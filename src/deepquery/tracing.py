"""可观测性：Langfuse 全链路追踪。

设计原则：
1. 可选依赖——未配置 LANGFUSE_* 环境变量或未安装 langfuse 包时，
   全部调用是零开销 no-op，离线测试与 CI 不受影响。
2. 追踪永远不能弄崩主流程——Langfuse 侧的所有调用都包在 try/except 里，
   上报失败只丢 trace，不丢查询。

启用：`uv sync --extra trace`，然后在 .env 填 LANGFUSE_PUBLIC_KEY /
LANGFUSE_SECRET_KEY（Langfuse Cloud 免费版或自托管均可）。
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Settings


class RunTrace:
    """单次 ask() 的追踪句柄。基类即 no-op 实现。"""

    def span(self, name: str, metadata: dict | None = None) -> None:
        """记录一个步骤事件（如一次 SQL 执行）。"""

    def generation(
        self,
        tag: str,
        messages: list[dict],
        output: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """记录一次 LLM 调用。"""

    def end(self, status: str = "", output: str = "", usage: dict | None = None) -> None:
        """结束本次运行的追踪。"""


class Tracer:
    """Tracer 工厂。基类即 no-op 实现。"""

    enabled = False

    def start_run(self, question: str) -> RunTrace:
        return RunTrace()


NOOP_TRACER = Tracer()


class _LangfuseRunTrace(RunTrace):
    def __init__(self, client: Any, root: Any):
        self._client = client
        self._root = root

    def span(self, name: str, metadata: dict | None = None) -> None:
        try:
            child = self._root.start_span(name=name, input=metadata or {})
            child.end()
        except Exception:  # 追踪失败绝不影响主流程
            pass

    def generation(self, tag, messages, output, model, prompt_tokens=0, completion_tokens=0):
        try:
            gen = self._root.start_generation(
                name=tag,
                model=model,
                input=messages,
                output=output,
                usage_details={"input": prompt_tokens, "output": completion_tokens},
            )
            gen.end()
        except Exception:
            pass

    def end(self, status="", output="", usage=None):
        try:
            self._root.update(output={"status": status, "answer": output, "usage": usage or {}})
            self._root.end()
            self._client.flush()
        except Exception:
            pass


class LangfuseTracer(Tracer):
    enabled = True

    def __init__(self, settings: "Settings"):
        from langfuse import Langfuse  # 可选依赖：uv sync --extra trace

        self._client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )

    def start_run(self, question: str) -> RunTrace:
        try:
            root = self._client.start_span(name="ask", input={"question": question})
            return _LangfuseRunTrace(self._client, root)
        except Exception:
            return RunTrace()


def build_tracer(settings: "Settings") -> Tracer:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return NOOP_TRACER
    try:
        return LangfuseTracer(settings)
    except ImportError:
        print(
            "[deepquery] 检测到 LANGFUSE_* 配置但未安装 langfuse 包，"
            "追踪已禁用。启用：uv sync --extra trace",
            file=sys.stderr,
        )
        return NOOP_TRACER
    except Exception as e:
        print(f"[deepquery] Langfuse 初始化失败，追踪已禁用: {e}", file=sys.stderr)
        return NOOP_TRACER
