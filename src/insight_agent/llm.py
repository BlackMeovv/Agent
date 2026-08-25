"""LLM 客户端：OpenAI 兼容接口 + 用量记账 + 指数退避重试。

约定：任何调用方必须传入本次运行的 UsageMeter，调用前做预算检查，
调用后记账——预算熔断因此对"每一次"模型调用都生效。
MockLLM 与真实客户端同接口，供离线测试与评测基建自检使用。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .budget import UsageMeter
from .config import Settings


@dataclass
class LLMReply:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class LLMError(RuntimeError):
    """重试耗尽后的最终失败。"""


def estimate_tokens(texts) -> int:
    """无 usage 时的保守 token 估算（约 4 字符/token）。"""
    return sum(len(t) for t in texts) // 4


class BaseLLM:
    model_name: str = "unknown"

    def chat(self, messages: list[dict], meter: UsageMeter, tag: str = "") -> LLMReply:
        raise NotImplementedError


class LLMClient(BaseLLM):
    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise LLMError(
                "LLM_API_KEY 未配置。请 `cp .env.example .env` 并填入你的 API Key；"
                "离线场景请使用 MockLLM。"
            )
        self._settings = settings
        self.model_name = settings.llm_model
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # 重试策略自己控制，便于记录与退避
        )

    def chat(self, messages: list[dict], meter: UsageMeter, tag: str = "") -> LLMReply:
        meter.check()
        settings = self._settings
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(settings.llm_max_retries + 1):
            start = time.monotonic()
            try:
                resp = self._client.chat.completions.create(
                    model=settings.llm_model,
                    messages=messages,
                    temperature=settings.llm_temperature,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                choices = getattr(resp, "choices", None)
                if not choices:
                    raise LLMError(f"LLM 返回空 choices（model={settings.llm_model}）")
                text = choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                if prompt_tokens == 0 and completion_tokens == 0:
                    # 上游不回 usage 时按字符保守估算——预算熔断不允许静默失效
                    prompt_tokens = estimate_tokens(str(m.get("content", "")) for m in messages)
                    completion_tokens = max(1, estimate_tokens([text]))
                    meter.unmetered_calls += 1
                meter.add(prompt_tokens, completion_tokens, tag=tag)
                return LLMReply(text, prompt_tokens, completion_tokens, latency_ms)
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                last_error = e
            except APIStatusError as e:
                # 5xx 可重试，4xx（如鉴权错误）直接失败
                if e.status_code < 500:
                    raise LLMError(f"LLM 调用失败（HTTP {e.status_code}）: {e}") from e
                last_error = e
            except LLMError:
                raise
            except OpenAIError as e:
                raise LLMError(f"LLM 调用失败: {e}") from e
            except Exception as e:  # 畸形响应等未知异常：包装而不是冲出 ask()
                raise LLMError(f"LLM 响应处理失败: {type(e).__name__}: {e}") from e
            if attempt < settings.llm_max_retries:
                time.sleep(delay)
                delay *= 2
        raise LLMError(f"LLM 调用重试 {settings.llm_max_retries} 次后仍失败: {last_error}") from last_error


class MockLLM(BaseLLM):
    """离线 mock：按脚本顺序吐回复。replies 用完后重复最后一条。"""

    model_name = "mock"

    def __init__(self, replies: list[str]):
        if not replies:
            raise ValueError("MockLLM 至少需要一条回复")
        self._replies = list(replies)
        self._i = 0
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], meter: UsageMeter, tag: str = "") -> LLMReply:
        meter.check()
        self.calls.append(messages)
        text = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        # 与真实客户端的无 usage 兜底同源，保证预算熔断在离线路径同样可测
        prompt_tokens = estimate_tokens(str(m.get("content", "")) for m in messages)
        completion_tokens = max(1, estimate_tokens([text]))
        meter.add(prompt_tokens, completion_tokens, tag=tag)
        return LLMReply(text, prompt_tokens, completion_tokens, latency_ms=0)
