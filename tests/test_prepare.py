"""BIRD/Spider 转换器 + 多库 runner 的离线端到端测试（自造迷你基准）。"""

import json
import sqlite3

import pytest

from insight_agent.evalkit.prepare import prepare, sample_cases
from insight_agent.evalkit.runner import load_cases, run_eval


@pytest.fixture()
def mini_bird_root(tmp_path):
    root = tmp_path / "bird_dev"
    db_dir = root / "dev_databases" / "shop"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "shop.sqlite")
    conn.executescript(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, price REAL);
        INSERT INTO items VALUES (1, 'a', 10.0), (2, 'b', 20.0), (3, 'c', 30.0);
        """
    )
    conn.commit()
    conn.close()
    dev = [
        {
            "question_id": 0,
            "db_id": "shop",
            "question": "有多少个商品？",
            "evidence": "商品存在 items 表",
            "SQL": "SELECT COUNT(*) FROM items",
            "difficulty": "simple",
        },
        {
            "question_id": 1,
            "db_id": "shop",
            "question": "最贵的商品叫什么？",
            "evidence": "",
            "SQL": "SELECT name FROM items ORDER BY price DESC LIMIT 1",
            "difficulty": "simple",
        },
        {
            "question_id": 2,
            "db_id": "shop",
            "question": "坏 gold（应被剔除）",
            "evidence": "",
            "SQL": "SELECT nope FROM items",
            "difficulty": "simple",
        },
    ]
    (root / "dev.json").write_text(json.dumps(dev, ensure_ascii=False), encoding="utf-8")
    return root


class TestPrepare:
    def test_convert_validate_and_write(self, mini_bird_root, tmp_path):
        out = tmp_path / "bird-mini.jsonl"
        info = prepare("bird", mini_bird_root, out)
        assert info["total"] == 3 and info["written"] == 2  # 坏 gold 被剔除
        assert any("bird-2" in p for p in info["problems"])

        cases = load_cases(out)
        assert cases[0]["id"] == "bird-0"
        assert "背景知识" in cases[0]["question"]  # evidence 注入
        assert "背景知识" not in cases[1]["question"]  # 空 evidence 不注入
        assert cases[0]["db"] == "dev_databases/shop/shop.sqlite"  # 相对根目录，可移植

    def test_sampling_deterministic(self):
        cases = [{"id": str(i)} for i in range(100)]
        a = sample_cases(cases, 10, seed=42)
        b = sample_cases(cases, 10, seed=42)
        c = sample_cases(cases, 10, seed=7)
        assert a == b and a != c and len(a) == 10


class TestMultiDbRunner:
    def test_gold_replay_on_prepared_bench(self, mini_bird_root, tmp_path, monkeypatch):
        """转换出的基准 + 逐 case 指定 db 的 runner，离线全链路必须满分。"""
        out = tmp_path / "bird-mini.jsonl"
        prepare("bird", mini_bird_root, out)
        monkeypatch.chdir(tmp_path)  # 避免报告写进仓库 eval/results
        report = run_eval(
            out, gold_replay=True, db_root=mini_bird_root, out_path=tmp_path / "r.json"
        )
        assert report["summary"]["cases"] == 2
        assert report["summary"]["ex_accuracy"] == 1.0

    def test_repeats_and_wilson_ci(self, mini_bird_root, tmp_path):
        out = tmp_path / "bird-mini.jsonl"
        prepare("bird", mini_bird_root, out)
        report = run_eval(
            out,
            gold_replay=True,
            db_root=mini_bird_root,
            out_path=tmp_path / "r.json",
            repeats=3,
            label="ci-check",
        )
        s = report["summary"]
        assert s["repeats"] == 3 and s["trials"] == 6
        assert s["per_repeat_accuracy"] == [1.0, 1.0, 1.0]
        assert s["wilson_low"] < 1.0 <= s["wilson_high"]  # 6 次全对也不该声称下界是 100%
        assert s["label"] == "ci-check"
        assert report["results"][0]["success_rate"] == 1.0
