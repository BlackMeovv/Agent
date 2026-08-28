from deepquery.agent import DeepQuery
from deepquery.llm import MockLLM
from deepquery.memory import MemoryStore


class TestMemoryStore:
    def test_remember_recall_forget(self, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        note_id = store.remember("u1", "销售额一律指已完成订单的成交金额")
        store.remember("u1", "默认只看 2025 年的数据")
        assert len(store.notes("u1")) == 2
        # 条目少时全部返回
        assert len(store.recall("u1", "本月销售额多少？")) == 2
        assert store.forget("u1", note_id)
        assert len(store.notes("u1")) == 1
        assert not store.forget("u1", 9999)

    def test_user_isolation(self, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        store.remember("u1", "只看华东区")
        assert store.notes("u2") == []
        assert store.recall("u2", "任何问题") == []
        assert not store.forget("u2", 1)  # 不能删别人的记忆

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "mem.sqlite"
        MemoryStore(path).remember("u1", "口径 A")
        assert MemoryStore(path).notes("u1")[0][1] == "口径 A"

    def test_duplicate_notes_injected_once(self, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        for _ in range(3):
            store.remember("u1", "销售额一律指已完成订单的成交金额")
        store.remember("u1", "默认只看 2025 年的数据")
        hits = store.recall("u1", "本月销售额多少？")
        assert hits.count("销售额一律指已完成订单的成交金额") == 1
        assert len(hits) == 2

    def test_bm25_selection_when_many(self, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        for note in ["销售额指成交金额", "毛利按成交价减成本", "会员等级金卡是 2", "城市默认全国", "日期格式 YYYY-MM-DD"]:
            store.remember("u1", note)
        hits = store.recall("u1", "这个月销售额是多少", top_n=2)
        assert len(hits) <= 2 and any("销售额" in h for h in hits)


class TestMemoryInjection:
    def test_memory_reaches_prompt(self, settings, db, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        store.remember("u1", "我说的客户默认指钻石会员（vip_level=3）")
        llm = MockLLM(["思路。\n```sql\nSELECT COUNT(*) FROM customers WHERE vip_level = 3\n```"])
        agent = DeepQuery(settings, db, llm, memory=store)
        agent.ask("客户有多少个？", generate_answer=False, user_id="u1")
        prompt = llm.calls[0][1]["content"]
        assert "口径偏好" in prompt and "钻石会员" in prompt

    def test_other_user_memory_not_leaked(self, settings, db, tmp_path):
        store = MemoryStore(tmp_path / "mem.sqlite")
        store.remember("u1", "u1 的私有口径")
        llm = MockLLM(["思路。\n```sql\nSELECT COUNT(*) FROM customers\n```"])
        agent = DeepQuery(settings, db, llm, memory=store)
        agent.ask("客户有多少个？", generate_answer=False, user_id="u2")
        assert "u1 的私有口径" not in llm.calls[0][1]["content"]
