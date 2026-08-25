"""Agent 编排：LangGraph 外层状态机 + 手写的修复内循环。

外层（LangGraph 负责确定性流转）：
    generate_sql → execute →（成功）→ answer
                          →（失败且还有额度）→ repair → execute ...
                          →（轮次/预算耗尽）→ fallback

内层（repair 节点内部是手写的 Reason-Act-Observe 循环）：
    观察全部历史尝试与结构化错误 → 生成修正 SQL
    → 重复 SQL 检测：与历史重复时注入"换思路"提示再试一次
    → 特例：上一轮是 empty_result 且模型原样重发，视为"确认数据为空"，接受为最终结果

可靠性设计都放在编排层（重试上限、预算熔断、终止条件），不依赖模型自觉。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph

from ..budget import BudgetExceeded, UsageMeter
from ..config import Settings
from ..guard import validate
from ..llm import BaseLLM, LLMError
from ..tools.contract import QueryResult
from ..tools.database import ReadOnlyDatabase
from . import prompts


@dataclass
class Attempt:
    sql_raw: str  # 模型输出的 SQL（守卫改写前）
    sql_final: str | None  # 守卫放行并改写后的 SQL；被拒时为 None
    ok: bool
    error_kind: str | None = None
    error_message: str | None = None
    result: QueryResult | None = None

    def describe(self, idx: int) -> str:
        status = "成功" if self.ok else f"[{self.error_kind}] {self.error_message}"
        return f"尝试 {idx}:\n```sql\n{self.sql_raw}\n```\n结果: {status}"


@dataclass
class RunOutcome:
    question: str
    status: str  # ok / ok_empty / failed / budget_exceeded
    answer: str = ""
    final_sql: str | None = None  # 实际执行的 SQL（守卫改写后，含注入的 LIMIT）
    predicted_sql: str | None = None  # 模型原始 SQL（评测打分用）
    result: QueryResult | None = None
    attempts: list[Attempt] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status in ("ok", "ok_empty")


class _State(TypedDict, total=False):
    question: str
    schema_context: str
    candidate_sql: str  # 待执行的 SQL（generate/repair 产出）
    generate_answer: bool  # 是否生成总结回答（评测时关掉省成本）
    attempts: list[Attempt]
    accept_empty: bool  # repair 确认空结果为最终答案
    give_up_reason: str
    status: str
    answer: str
    meter: Any  # UsageMeter（对象通道，就地累加）


_CODE_BLOCK = re.compile(r"```([a-zA-Z0-9_-]*)[ \t]*\n?(.*?)```", re.DOTALL)
_SQL_HEAD = re.compile(r"^\s*(select|with)\b", re.IGNORECASE | re.DOTALL)


def extract_sql(text: str) -> str:
    """从模型回复中提取 SQL。

    模型输出形态多样（多个代码块、```sqlite/无语言标签围栏、混入 json 块），
    按优先级取：sql/sqlite 标签的块 → 以 SELECT/WITH 开头的块 → 第一个块 → 整段文本。
    """
    blocks = [(lang.lower(), body.strip()) for lang, body in _CODE_BLOCK.findall(text or "")]
    candidate = next((body for lang, body in blocks if lang in ("sql", "sqlite") and body), None)
    if candidate is None:
        candidate = next((body for _lang, body in blocks if _SQL_HEAD.match(body)), None)
    if candidate is None and blocks:
        candidate = blocks[0][1]
    if candidate is None:
        candidate = text or ""
    return candidate.strip().rstrip(";").strip()


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";")).lower()


class InsightAgent:
    def __init__(self, settings: Settings, db: ReadOnlyDatabase, llm: BaseLLM):
        self.settings = settings
        self.db = db
        self.llm = llm
        self._allowed_tables = set(db.table_names())
        self._schema_context = db.schema_text()
        self._graph = self._build_graph()

    # ---------- public ----------

    def ask(self, question: str, generate_answer: bool = True) -> RunOutcome:
        """回答一个自然语言问题。generate_answer=False 时跳过总结节点（评测省成本）。"""
        start = time.monotonic()
        meter = UsageMeter(
            price_input_per_m=self.settings.llm_price_input_per_m,
            price_output_per_m=self.settings.llm_price_output_per_m,
            max_tokens=self.settings.agent_max_tokens_per_run,
            max_cost=self.settings.agent_max_cost_per_run,
        )
        state: _State = {
            "question": question,
            "schema_context": self._schema_context,
            "attempts": [],
            "generate_answer": generate_answer,
            "meter": meter,
        }
        try:
            # 每轮修复消耗 repair+execute 两个 superstep，上限必须跟随配置放大
            final = self._graph.invoke(
                state,
                config={"recursion_limit": 2 * self.settings.agent_max_repair_rounds + 12},
            )
        except GraphRecursionError:
            final = {"attempts": [], "status": "failed", "answer": "内部编排步数超限，已终止。"}
        attempts: list[Attempt] = final.get("attempts", [])
        last_ok = next((a for a in reversed(attempts) if a.ok), None)
        executed_sql, raw_sql = self._pick_final(final, attempts, last_ok)
        outcome = RunOutcome(
            question=question,
            status=final.get("status", "failed"),
            answer=final.get("answer", ""),
            final_sql=executed_sql,
            predicted_sql=raw_sql,
            result=last_ok.result if last_ok else None,
            attempts=attempts,
            usage=meter.snapshot(),
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return outcome

    @staticmethod
    def _pick_final(
        final: _State, attempts: list[Attempt], last_ok: Attempt | None
    ) -> tuple[str | None, str | None]:
        """返回 (实际执行的守卫改写版 SQL, 模型原始 SQL)。评测打分用后者——
        守卫注入的 LIMIT 是生产安全措施，不应影响 EX 判定。"""
        if last_ok:
            return last_ok.sql_final, last_ok.sql_raw
        if final.get("accept_empty"):
            # 空结果被确认为最终答案：取最后一次守卫放行的 SQL
            for a in reversed(attempts):
                if a.sql_final:
                    return a.sql_final, a.sql_raw
        return None, None

    # ---------- graph ----------

    def _build_graph(self):
        g = StateGraph(_State)
        g.add_node("generate_sql", self._node_generate_sql)
        g.add_node("execute", self._node_execute)
        g.add_node("repair", self._node_repair)
        g.add_node("summarize", self._node_answer)
        g.add_node("fallback", self._node_fallback)

        g.set_entry_point("generate_sql")
        g.add_conditional_edges(
            "generate_sql",
            lambda s: "fallback" if s.get("status") in ("budget_exceeded", "failed") else "execute",
            {"execute": "execute", "fallback": "fallback"},
        )
        g.add_conditional_edges(
            "execute",
            self._route_after_execute,
            {"answer": "summarize", "repair": "repair", "fallback": "fallback"},
        )
        g.add_conditional_edges(
            "repair",
            self._route_after_repair,
            {"execute": "execute", "answer": "summarize", "fallback": "fallback"},
        )
        g.add_edge("summarize", END)
        g.add_edge("fallback", END)
        return g.compile()

    # ---------- nodes ----------

    def _node_generate_sql(self, state: _State) -> _State:
        messages = [
            {"role": "system", "content": prompts.SQL_SYSTEM},
            {
                "role": "user",
                "content": prompts.SQL_USER_TEMPLATE.format(
                    schema=state["schema_context"], question=state["question"]
                ),
            },
        ]
        try:
            reply = self.llm.chat(messages, state["meter"], tag="generate_sql")
        except BudgetExceeded:
            return {"status": "budget_exceeded", "give_up_reason": "预算超限"}
        except LLMError as e:
            return {"status": "failed", "give_up_reason": f"LLM 调用失败: {e}"}
        return {"candidate_sql": extract_sql(reply.text)}

    def _node_execute(self, state: _State) -> _State:
        sql_raw = state.get("candidate_sql", "")
        verdict = validate(
            sql_raw,
            allowed_tables=self._allowed_tables,
            max_rows=self.settings.sql_max_rows,
        )
        if not verdict.allowed:
            attempt = Attempt(
                sql_raw=sql_raw,
                sql_final=None,
                ok=False,
                error_kind=verdict.error_kind,
                error_message=verdict.reason,
            )
        else:
            result = self.db.run_query(verdict.sql)
            attempt = Attempt(
                sql_raw=sql_raw,
                sql_final=verdict.sql,
                ok=result.ok,
                error_kind=result.error_kind,
                error_message=result.error_message,
                result=result,
            )
        return {"attempts": state["attempts"] + [attempt]}

    def _route_after_execute(self, state: _State) -> str:
        if state.get("status") in ("budget_exceeded", "failed"):
            return "fallback"
        last = state["attempts"][-1]
        if last.ok:
            return "answer"
        meter: UsageMeter = state["meter"]
        if meter.exceeded():
            return "fallback"
        # 首次生成占 1 次，之后每轮 repair 占 1 次
        if len(state["attempts"]) > self.settings.agent_max_repair_rounds:
            return "fallback"
        return "repair"

    def _node_repair(self, state: _State) -> _State:
        """手写修复内循环：观察历史 → 生成修正 SQL → 重复检测（最多提醒一次）。"""
        attempts = state["attempts"]
        seen = {normalize_sql(a.sql_raw) for a in attempts}
        last = attempts[-1]
        history = "\n\n".join(a.describe(i + 1) for i, a in enumerate(attempts))
        messages = [
            {"role": "system", "content": prompts.SQL_SYSTEM},
            {
                "role": "user",
                "content": prompts.SQL_USER_TEMPLATE.format(
                    schema=state["schema_context"], question=state["question"]
                ),
            },
            {"role": "user", "content": prompts.REPAIR_USER_TEMPLATE.format(attempts=history)},
        ]
        for inner_round in range(2):  # 第二轮带"换思路"提醒
            try:
                reply = self.llm.chat(messages, state["meter"], tag="repair")
            except BudgetExceeded:
                return {"status": "budget_exceeded", "give_up_reason": "预算超限"}
            except LLMError as e:
                return {"status": "failed", "give_up_reason": f"LLM 调用失败: {e}"}
            candidate = extract_sql(reply.text)
            resent_last = normalize_sql(candidate) == normalize_sql(last.sql_raw)
            if resent_last and last.error_kind == "empty_result" and last.sql_final:
                # 模型【原样重发上一条】空结果 SQL：确认数据确实为空，接受为最终答案。
                # 注意必须严格等于上一条——重发更早的失败 SQL 是模型混乱，不是确认。
                return {"accept_empty": True}
            if normalize_sql(candidate) not in seen:
                return {"candidate_sql": candidate}
            messages = messages + [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": prompts.REPAIR_NUDGE},
            ]
        return {"give_up_reason": "模型反复生成相同的失败 SQL，停止修复"}

    def _route_after_repair(self, state: _State) -> str:
        if state.get("status") in ("budget_exceeded", "failed"):
            return "fallback"
        if state.get("accept_empty"):
            return "answer"
        if state.get("give_up_reason"):
            return "fallback"
        return "execute"

    def _node_answer(self, state: _State) -> _State:
        attempts = state["attempts"]
        generate_answer = state.get("generate_answer", True)
        last_ok = next((a for a in reversed(attempts) if a.ok), None)
        if state.get("accept_empty") and last_ok is None:
            answer = "查询执行成功，但没有符合条件的数据。" if generate_answer else ""
            return {"status": "ok_empty", "answer": answer}

        assert last_ok is not None and last_ok.result is not None
        if not generate_answer:
            return {"status": "ok", "answer": ""}
        messages = [
            {"role": "system", "content": prompts.ANSWER_SYSTEM},
            {
                "role": "user",
                "content": prompts.ANSWER_USER_TEMPLATE.format(
                    question=state["question"],
                    sql=last_ok.sql_final,
                    result=last_ok.result.preview(max_rows=20),
                ),
            },
        ]
        try:
            reply = self.llm.chat(messages, state["meter"], tag="answer")
        except (BudgetExceeded, LLMError):
            # 总结失败不影响查询本身的成功：降级为直接给数据预览
            return {"status": "ok", "answer": f"查询成功，结果如下：\n{last_ok.result.preview()}"}
        return {"status": "ok", "answer": reply.text.strip()}

    def _node_fallback(self, state: _State) -> _State:
        """无 LLM 降级收尾：把已知信息如实交代，绝不编造。"""
        attempts = state["attempts"]
        status = state.get("status") or "failed"
        reason = state.get("give_up_reason", "自动修复轮次已用尽")
        # 路由函数不能写状态：经 _route_after_execute 因预算超限进来时在此落真实原因
        meter: UsageMeter | None = state.get("meter")
        if status == "failed" and not state.get("give_up_reason") and meter and meter.exceeded():
            status, reason = "budget_exceeded", "预算超限"
        lines = [f"未能得到可靠的查询结果（{reason}）。"]
        if attempts:
            last = attempts[-1]
            lines.append(f"最后一次尝试的 SQL：\n{last.sql_raw}")
            if last.error_message:
                lines.append(f"错误信息：[{last.error_kind}] {last.error_message}")
        return {"status": status if status != "ok" else "failed", "answer": "\n".join(lines)}
