"""自建业务评测集生成器测试。"""

from deepquery.evalkit.business_set import generate
from deepquery.evalkit.runner import load_cases, run_eval


class TestBusinessSet:
    def test_generation_counts_and_split(self, demo_db_path, tmp_path):
        info = generate(demo_db_path, out_dir=tmp_path)
        assert info["total"] >= 200
        assert info["dev"] + info["holdout"] == info["total"]
        dev = load_cases(info["files"]["business-dev"])
        holdout = load_cases(info["files"]["business-holdout"])
        assert not ({c["id"] for c in dev} & {c["id"] for c in holdout})  # 严格不相交
        assert any("jargon" in c["tags"] for c in dev)  # 黑话题必须存在

    def test_deterministic(self, demo_db_path, tmp_path):
        a = generate(demo_db_path, out_dir=tmp_path / "a")
        b = generate(demo_db_path, out_dir=tmp_path / "b")
        text_a = open(a["files"]["business-dev"], encoding="utf-8").read()
        text_b = open(b["files"]["business-dev"], encoding="utf-8").read()
        assert text_a == text_b

    def test_gold_replay_on_subset(self, demo_db_path, tmp_path, monkeypatch):
        info = generate(demo_db_path, out_dir=tmp_path)
        monkeypatch.setenv("DB_PATH", str(demo_db_path))
        from deepquery.config import get_settings

        get_settings.cache_clear()
        try:
            report = run_eval(
                info["files"]["business-dev"],
                gold_replay=True,
                limit=15,
                out_path=tmp_path / "r.json",
            )
        finally:
            get_settings.cache_clear()
        assert report["summary"]["ex_accuracy"] == 1.0
