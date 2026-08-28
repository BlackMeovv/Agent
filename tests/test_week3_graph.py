"""Week 3 图接线测试：Schema RAG、按错误类型的修复提示、防幻觉拦截。"""

from insight_agent.agent import InsightAgent
from insight_agent.llm import MockLLM


def make_agent(settings, db, replies):
    llm = MockLLM(replies)
    return InsightAgent(settings, db, llm), llm


def sql_reply(sql):
    return f"思路。\n```sql\n{sql}\n```"


GOOD_SQL = "SELECT COUNT(*) FROM customers WHERE city = '上海'"


def shanghai_count(db) -> int:
    """测试里的数字必须从库里取——硬编码的数字会被防幻觉校验正确地拦下。"""
    return db.run_query(GOOD_SQL).rows[0][0]


class TestSchemaRag:
    def test_auto_mode_keeps_full_schema_for_small_db(self, settings, db):
        # 演示库 6 张表，top_k 默认 6：auto 不启用检索
        agent, llm = make_agent(settings, db, [sql_reply(GOOD_SQL)])
        outcome = agent.ask("上海的客户数？", generate_answer=False)
        assert outcome.selected_tables is None
        assert "CREATE TABLE payments" in llm.calls[0][1]["content"]  # 全量 schema

    def test_forced_on_selects_topk(self, settings, db):
        rag = settings.model_copy(update={"schema_rag": "on", "schema_rag_top_k": 2})
        agent, llm = make_agent(rag, db, [sql_reply("SELECT method, COUNT(*) FROM payments GROUP BY method")])
        outcome = agent.ask("每种支付方式有多少笔支付？", generate_answer=False)
        assert outcome.selected_tables is not None and len(outcome.selected_tables) == 2
        assert "payments" in outcome.selected_tables
        prompt = llm.calls[0][1]["content"]
        assert "CREATE TABLE payments" in prompt
        # 只喂了 2 张表：6 张表的全量 DDL 不应全部出现
        assert prompt.count("CREATE TABLE") == 2

    def test_off_mode(self, settings, db):
        off = settings.model_copy(update={"schema_rag": "off", "schema_rag_top_k": 2})
        agent, _ = make_agent(off, db, [sql_reply(GOOD_SQL)])
        outcome = agent.ask("上海的客户数？", generate_answer=False)
        assert outcome.selected_tables is None

    def test_glossary_injected(self, settings, db, tmp_path):
        g = tmp_path / "glossary.jsonl"
        g.write_text('{"term": "成交额", "definition": "quantity*unit_price 求和"}\n', encoding="utf-8")
        cfg = settings.model_copy(update={"glossary_path": str(g)})
        agent, llm = make_agent(cfg, db, [sql_reply(GOOD_SQL)])
        agent.ask("本月成交额是多少？", generate_answer=False)
        assert "业务字典" in llm.calls[0][1]["content"]
        assert "quantity*unit_price" in llm.calls[0][1]["content"]


class TestRepairHints:
    def test_error_specific_hint_in_repair_prompt(self, settings, db):
        agent, llm = make_agent(
            settings,
            db,
            [sql_reply("SELECT nope FROM customers"), sql_reply(GOOD_SQL)],
        )
        outcome = agent.ask("上海的客户数？", generate_answer=False)
        assert outcome.status == "ok"
        repair_prompt = llm.calls[1][-1]["content"]
        assert "列名不存在" in repair_prompt  # no_such_column 的针对性提示


class TestHallucinationGate:
    def test_fabricated_number_blocked_after_retry(self, settings, db):
        cnt = shanghai_count(db)
        agent, _ = make_agent(
            settings,
            db,
            [
                sql_reply(GOOD_SQL),
                f"上海共有 {cnt} 位客户，占全国的 37.9%。",  # 37.9% 无出处
                "重写后依然声称占比 37.9%。",  # 重写仍编造
            ],
        )
        outcome = agent.ask("上海的客户一共有多少个？")
        assert outcome.status == "ok"
        assert outcome.hallucination_blocked
        assert "37.9%" not in outcome.answer  # 降级为确定性结果预览
        assert outcome.usage["llm_calls"] == 3  # 生成 + 总结 + 一次重写

    def test_retry_fixes_answer(self, settings, db):
        cnt = shanghai_count(db)
        agent, _ = make_agent(
            settings,
            db,
            [
                sql_reply(GOOD_SQL),
                f"上海共有 {cnt} 位客户，占全国的 37.9%。",
                f"上海共有 {cnt} 位客户。",  # 重写后干净
            ],
        )
        outcome = agent.ask("上海的客户一共有多少个？")
        assert not outcome.hallucination_blocked
        assert outcome.answer == f"上海共有 {cnt} 位客户。"

    def test_clean_answer_untouched(self, settings, db):
        cnt = shanghai_count(db)
        agent, _ = make_agent(settings, db, [sql_reply(GOOD_SQL), f"上海共有 {cnt} 位客户。"])
        outcome = agent.ask("上海的客户一共有多少个？")
        assert not outcome.hallucination_blocked
        assert outcome.usage["llm_calls"] == 2  # 干净回答不触发重写

    def test_verify_can_be_disabled(self, settings, db):
        cfg = settings.model_copy(update={"answer_verify": False})
        agent, _ = make_agent(cfg, db, [sql_reply(GOOD_SQL), "占比 37.9%。"])
        outcome = agent.ask("上海的客户一共有多少个？")
        assert not outcome.hallucination_blocked
        assert outcome.answer == "占比 37.9%。"


class TestRunnerTableRecall:
    def test_recall_metric(self, settings, db, demo_db_path, tmp_path, monkeypatch):
        import json

        from insight_agent.evalkit.runner import run_eval

        cases = tmp_path / "cases.jsonl"
        cases.write_text(
            json.dumps(
                {
                    "id": "c1",
                    "question": "每种支付方式有多少笔支付？",
                    "gold_sql": "SELECT method, COUNT(*) FROM payments GROUP BY method",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("SCHEMA_RAG", "on")
        monkeypatch.setenv("SCHEMA_RAG_TOP_K", "2")
        monkeypatch.setenv("DB_PATH", str(demo_db_path))
        from insight_agent.config import get_settings

        get_settings.cache_clear()
        try:
            report = run_eval(cases, gold_replay=True, out_path=tmp_path / "r.json")
        finally:
            get_settings.cache_clear()
        assert report["summary"]["ex_accuracy"] == 1.0
        assert report["summary"]["avg_table_recall"] == 1.0
        assert report["results"][0]["table_recall"] == 1.0


class TestSchemaRagAutoBySize:
    """auto 判据按 schema 体积而非表数——BIRD 消融驱动的架构决策回归测试。"""

    def test_many_small_tables_stay_full(self, settings, db):
        # 6 表 > top_k=2，但全量体积远小于阈值：不检索，直供全量 schema
        cfg = settings.model_copy(update={"schema_rag": "auto", "schema_rag_top_k": 2})
        agent, llm = make_agent(cfg, db, [sql_reply(GOOD_SQL)])
        outcome = agent.ask("上海的客户数？", generate_answer=False)
        assert outcome.selected_tables is None
        assert llm.calls[0][1]["content"].count("CREATE TABLE") == 6

    def test_oversized_schema_enables_rag(self, settings, db):
        cfg = settings.model_copy(
            update={"schema_rag": "auto", "schema_rag_top_k": 2, "schema_rag_auto_max_chars": 10}
        )
        agent, _ = make_agent(cfg, db, [sql_reply(GOOD_SQL)])
        outcome = agent.ask("上海的客户数？", generate_answer=False)
        assert outcome.selected_tables is not None and len(outcome.selected_tables) == 2
