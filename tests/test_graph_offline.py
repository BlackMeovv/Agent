"""用 MockLLM 离线走通 agent 全链路：不需要任何 API Key。"""

from insight_agent.agent import InsightAgent
from insight_agent.llm import MockLLM


def make_agent(settings, db, replies):
    return InsightAgent(settings, db, MockLLM(replies))


def sql_reply(sql: str) -> str:
    return f"思路说明。\n```sql\n{sql}\n```"


GOOD_SQL = "SELECT COUNT(*) FROM customers WHERE city = '上海'"


class TestHappyPath:
    def test_first_try_success(self, settings, db):
        agent = make_agent(settings, db, [sql_reply(GOOD_SQL), "上海共有 20 位客户。"])
        outcome = agent.ask("上海的客户一共有多少个？")
        assert outcome.status == "ok"
        assert outcome.final_sql and "customers" in outcome.final_sql
        assert len(outcome.attempts) == 1
        assert outcome.answer == "上海共有 20 位客户。"
        assert outcome.usage["llm_calls"] == 2  # 生成 + 总结

    def test_skip_answer_saves_a_call(self, settings, db):
        agent = make_agent(settings, db, [sql_reply(GOOD_SQL)])
        outcome = agent.ask("上海的客户一共有多少个？", generate_answer=False)
        assert outcome.status == "ok" and outcome.answer == ""
        assert outcome.usage["llm_calls"] == 1


class TestRepairLoop:
    def test_bad_column_then_repaired(self, settings, db):
        agent = make_agent(
            settings,
            db,
            [
                sql_reply("SELECT COUNT(*) FROM customers WHERE town = '上海'"),  # no such column
                sql_reply(GOOD_SQL),
            ],
        )
        outcome = agent.ask("上海的客户一共有多少个？", generate_answer=False)
        assert outcome.status == "ok"
        assert len(outcome.attempts) == 2
        assert outcome.attempts[0].error_kind == "no_such_column"

    def test_guard_rejection_then_repaired(self, settings, db):
        agent = make_agent(
            settings,
            db,
            [sql_reply("DELETE FROM customers"), sql_reply(GOOD_SQL)],
        )
        outcome = agent.ask("上海的客户一共有多少个？", generate_answer=False)
        assert outcome.status == "ok"
        assert outcome.attempts[0].error_kind == "guard_rejected"

    def test_repeated_failure_gives_up(self, settings, db):
        bad = sql_reply("SELECT nope FROM customers")
        agent = make_agent(settings, db, [bad])  # MockLLM 之后一直重复同一条
        outcome = agent.ask("问题", generate_answer=False)
        assert outcome.status == "failed"
        assert outcome.final_sql is None
        # 初次失败后进入 repair，重复检测触发提醒再试一次仍重复 → 放弃，不该跑满轮次上限
        assert len(outcome.attempts) == 1

    def test_max_repair_rounds_respected(self, settings, db):
        # 每轮都是不同的坏 SQL：修满上限后 fallback
        replies = [
            sql_reply("SELECT a FROM customers"),
            sql_reply("SELECT b FROM customers"),
            sql_reply("SELECT c FROM customers"),
            sql_reply("SELECT d FROM customers"),
            sql_reply("SELECT e FROM customers"),
        ]
        agent = make_agent(settings, db, replies)
        outcome = agent.ask("问题", generate_answer=False)
        assert outcome.status == "failed"
        assert len(outcome.attempts) == 1 + settings.agent_max_repair_rounds


class TestEmptyResult:
    def test_empty_confirmed_becomes_final(self, settings, db):
        empty_sql = "SELECT * FROM customers WHERE city = '月球'"
        agent = make_agent(settings, db, [sql_reply(empty_sql)])  # 修复时原样重发同一条
        outcome = agent.ask("月球的客户有哪些？", generate_answer=False)
        assert outcome.status == "ok_empty"
        assert outcome.final_sql is not None

    def test_empty_then_fixed(self, settings, db):
        agent = make_agent(
            settings,
            db,
            [
                sql_reply("SELECT * FROM customers WHERE city = 'Shanghai'"),  # 值写错 → 空
                sql_reply(GOOD_SQL),
            ],
        )
        outcome = agent.ask("上海的客户一共有多少个？", generate_answer=False)
        assert outcome.status == "ok"
        assert outcome.attempts[0].error_kind == "empty_result"


class TestBudget:
    def test_budget_circuit_breaker(self, settings, db):
        tight = settings.model_copy(update={"agent_max_tokens_per_run": 1})
        agent = make_agent(tight, db, [sql_reply("SELECT bad FROM customers")])
        outcome = agent.ask("问题", generate_answer=False)
        # 第一次调用后预算即超限：不允许再产生新的 LLM 调用，且状态必须是明确的枚举值
        assert outcome.usage["llm_calls"] == 1
        assert outcome.status == "budget_exceeded"
