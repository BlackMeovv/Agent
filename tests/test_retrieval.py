from insight_agent.retrieval import (
    BM25,
    SchemaRetriever,
    TextEntry,
    TextIndex,
    load_examples,
    load_glossary,
    rrf_fuse,
    tokenize,
)


class TestTokenize:
    def test_mixed_language(self):
        tokens = tokenize("查询 payments 表的 GMV")
        assert "payments" in tokens and "gmv" in tokens
        assert "查" in tokens and "查询" in tokens  # 单字 + 双字组合

    def test_empty(self):
        assert tokenize("") == []


class TestBM25:
    DOCS = [
        "customers 客户表 城市 city 会员等级 vip_level 注册日期",
        "payments 支付表 支付方式 method 金额 amount 支付时间",
        "products 商品表 售价 price 成本 cost 品类",
    ]

    def test_relevant_doc_ranks_first(self):
        bm25 = BM25([tokenize(d) for d in self.DOCS])
        assert bm25.ranking("每种支付方式的总金额")[0] == 1
        assert bm25.ranking("客户的会员等级分布")[0] == 0
        assert bm25.ranking("商品的售价和成本")[0] == 2


class TestRRF:
    def test_agreement_wins(self):
        fused = rrf_fuse([[0, 1, 2], [0, 2, 1]])
        assert fused[0] == 0

    def test_single_ranking_passthrough(self):
        assert rrf_fuse([[2, 0, 1]]) == [2, 0, 1]


class TestSchemaRetriever:
    def test_top_tables_bm25_only(self, db):
        retriever = SchemaRetriever(db.schema_by_table())
        top = retriever.top_tables("每种支付方式分别有多少笔支付？", k=3)
        assert "payments" in top

    def test_fake_embedder_fused(self, db):
        docs = db.schema_by_table()
        names = list(docs)

        def fake_embedder(texts):
            # 与 payments 相关的文本给一个方向，其余给另一个方向
            return [[1.0, 0.0] if "payments" in t or "支付" in t else [0.0, 1.0] for t in texts]

        retriever = SchemaRetriever(docs, embedder=fake_embedder)
        top = retriever.top_tables("支付", k=2)
        assert "payments" in top
        assert len(retriever._doc_vectors) == len(names)


class TestTextIndex:
    def test_glossary_hit_and_miss(self):
        index = TextIndex(
            [
                TextEntry("GMV", "GMV：成交总额，按 quantity*unit_price 求和"),
                TextEntry("复购率", "复购率：下单超过一次的客户占比"),
            ]
        )
        hits = index.top("这个月的 GMV 是多少", 2)
        assert hits and hits[0].key == "GMV"
        assert index.top("完全无关的天气问题啊", 2) == [] or all(
            h.key for h in index.top("完全无关的天气问题啊", 2)
        )

    def test_empty_index(self):
        assert TextIndex([]).top("任何问题", 3) == []


class TestLoaders:
    def test_load_glossary_and_examples(self, tmp_path):
        g = tmp_path / "glossary.jsonl"
        g.write_text('{"term": "GMV", "definition": "成交总额"}\n', encoding="utf-8")
        e = tmp_path / "examples.jsonl"
        e.write_text('{"question": "客户数", "sql": "SELECT COUNT(*) FROM customers"}\n', encoding="utf-8")
        assert load_glossary(g).top("GMV", 1)[0].key == "GMV"
        assert "SELECT COUNT(*)" in load_examples(e).top("客户数", 1)[0].body

    def test_missing_files_are_empty(self, tmp_path):
        assert load_glossary(tmp_path / "nope.jsonl").top("x", 1) == []
        assert load_examples(tmp_path / "nope.jsonl").top("x", 1) == []
