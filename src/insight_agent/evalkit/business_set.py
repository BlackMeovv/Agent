"""自建业务评测集生成器：基于演示库的参数化模板，生成 200+ 条"业务黑话"问题。

    python -m insight_agent.evalkit.business_set     # 或 make business-set

设计：
- 模板 × 参数组合展开，每条 gold 生成时逐条执行校验，空结果/报错直接剔除；
- 固定 seed 打乱后按 70/30 切成 dev / holdout 两份——调 prompt 只看 dev，
  简历数字用 holdout 复核，防止对评测集过拟合；
- 刻意使用业务字典里的黑话（成交金额/毛利/沉默客户/金卡及以上），
  专门考察"口径翻译"能力——这是公开基准没有、真实业务里最常错的部分。
- 模板化生成的问题表述偏规整；投产前建议人工把其中一部分改写成更口语的问法。
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from ..demo_data import DEFAULT_PATH as DEMO_DB_PATH

_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "重庆"]
_CATEGORIES = ["手机数码", "家用电器", "服饰鞋包", "美妆个护", "食品生鲜", "图书文娱"]
_STATUSES = ["completed", "shipped", "pending", "cancelled"]
_METHODS = ["alipay", "wechat", "card"]
_MONTHS = [f"2025-0{m}" for m in range(1, 7)]
_MONTH_CN = {f"2025-0{m}": f"2025年{m}月" for m in range(1, 7)}
_TOPNS = [3, 5, 10]

SEED = 42
DEV_RATIO = 0.7


def _templates() -> list[tuple[str, str, list[str]]]:
    """返回 (question, gold_sql, tags) 列表。金额口径与 eval/knowledge/glossary.jsonl 一致。"""
    out: list[tuple[str, str, list[str]]] = []

    for city in _CITIES:
        out.append((f"{city}的客户一共有多少个？", f"SELECT COUNT(*) FROM customers WHERE city = '{city}'", ["filter"]))
        out.append((
            f"{city}的客户总共下了多少笔订单？",
            f"SELECT COUNT(*) FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.city = '{city}'",
            ["join"],
        ))
        out.append((
            f"{city}的客户支付总金额是多少？",
            f"SELECT SUM(p.amount) FROM payments p JOIN orders o ON p.order_id = o.id JOIN customers c ON o.customer_id = c.id WHERE c.city = '{city}'",
            ["join", "money"],
        ))
        out.append((
            f"{city}的客户平均单笔支付金额是多少？",
            f"SELECT AVG(p.amount) FROM payments p JOIN orders o ON p.order_id = o.id JOIN customers c ON o.customer_id = c.id WHERE c.city = '{city}'",
            ["join", "money"],
        ))
        out.append((
            f"{city}的客户中钻石会员有多少个？",
            f"SELECT COUNT(*) FROM customers WHERE city = '{city}' AND vip_level = 3",
            ["filter"],
        ))
        out.append((
            f"{city}的客户里下过已完成订单的有多少个？",
            f"SELECT COUNT(DISTINCT c.id) FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.city = '{city}' AND o.status = 'completed'",
            ["join", "jargon"],
        ))
        for status in ("completed", "cancelled"):
            out.append((
                f"{city}的客户下的订单中，状态为 {status} 的有多少笔？",
                f"SELECT COUNT(*) FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.city = '{city}' AND o.status = '{status}'",
                ["join", "filter"],
            ))

    for cat in _CATEGORIES:
        out.append((
            f"{cat}品类里售价最贵的商品是什么？给出名称和售价。",
            f"SELECT p.name, p.price FROM products p JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}' ORDER BY p.price DESC LIMIT 1",
            ["join", "sort"],
        ))
        out.append((
            f"{cat}品类下一共有多少个商品？",
            f"SELECT COUNT(*) FROM products p JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}'",
            ["join"],
        ))
        out.append((
            f"{cat}品类的成交金额是多少？",
            f"SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}'",
            ["join", "money", "jargon"],
        ))
        out.append((
            f"{cat}品类的毛利是多少？",
            f"SELECT SUM((oi.unit_price - p.cost) * oi.quantity) FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}'",
            ["join", "money", "jargon"],
        ))
        out.append((
            f"{cat}品类中销量最高的商品是什么？给出名称和销量。",
            f"SELECT p.name, SUM(oi.quantity) AS qty FROM order_items oi JOIN products p ON oi.product_id = p.id JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}' GROUP BY p.id ORDER BY qty DESC LIMIT 1",
            ["join", "sort"],
        ))
        out.append((
            f"{cat}品类的商品平均售价是多少？",
            f"SELECT AVG(p.price) FROM products p JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}'",
            ["join"],
        ))

    for month in _MONTHS:
        cn = _MONTH_CN[month]
        out.append((
            f"{cn}一共产生了多少笔订单？",
            f"SELECT COUNT(*) FROM orders WHERE strftime('%Y-%m', order_date) = '{month}'",
            ["date"],
        ))
        out.append((
            f"{cn}的支付总金额是多少？",
            f"SELECT SUM(amount) FROM payments WHERE strftime('%Y-%m', paid_at) = '{month}'",
            ["date", "money"],
        ))
        out.append((
            f"金卡及以上客户在{cn}的支付总金额是多少？",
            f"SELECT SUM(p.amount) FROM payments p JOIN orders o ON p.order_id = o.id JOIN customers c ON o.customer_id = c.id WHERE c.vip_level >= 2 AND strftime('%Y-%m', p.paid_at) = '{month}'",
            ["date", "money", "jargon"],
        ))
        out.append((
            f"{cn}各支付方式的支付金额分别是多少？",
            f"SELECT method, SUM(amount) FROM payments WHERE strftime('%Y-%m', paid_at) = '{month}' GROUP BY method",
            ["date", "group", "money"],
        ))

    for method in _METHODS:
        out.append((
            f"支付方式为 {method} 的支付一共有多少笔、总金额多少？",
            f"SELECT COUNT(*), SUM(amount) FROM payments WHERE method = '{method}'",
            ["filter", "money"],
        ))
        out.append((
            f"{method} 支付的平均单笔金额是多少？",
            f"SELECT AVG(amount) FROM payments WHERE method = '{method}'",
            ["filter", "money"],
        ))

    for vip in range(4):
        out.append((
            f"会员等级为 {vip} 的客户有多少人？",
            f"SELECT COUNT(*) FROM customers WHERE vip_level = {vip}",
            ["filter"],
        ))

    for status in _STATUSES:
        out.append((
            f"状态为 {status} 的订单一共有多少笔？",
            f"SELECT COUNT(*) FROM orders WHERE status = '{status}'",
            ["filter"],
        ))

    for n in _TOPNS:
        out.append((
            f"下单次数最多的前{n}名客户是谁？给出客户名和下单次数，次数相同按客户名排序。",
            f"SELECT c.name, COUNT(*) AS cnt FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.id ORDER BY cnt DESC, c.name LIMIT {n}",
            ["join", "sort"],
        ))
        out.append((
            f"销量最高的前{n}个商品是哪些？给出商品名和销量。",
            f"SELECT p.name, SUM(oi.quantity) AS qty FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.id ORDER BY qty DESC LIMIT {n}",
            ["join", "sort"],
        ))
        out.append((
            f"支付总金额最高的前{n}个城市是哪几个？给出城市和金额。",
            f"SELECT c.city, SUM(p.amount) AS total FROM payments p JOIN orders o ON p.order_id = o.id JOIN customers c ON o.customer_id = c.id GROUP BY c.city ORDER BY total DESC LIMIT {n}",
            ["join", "sort", "money"],
        ))

    # 交叉维度：城市 × 月份、品类 × 月份（更接近真实取数需求的多条件问法）
    for city in _CITIES[:5]:
        for month in _MONTHS:
            cn = _MONTH_CN[month]
            out.append((
                f"{city}的客户在{cn}的支付总金额是多少？",
                f"SELECT SUM(p.amount) FROM payments p JOIN orders o ON p.order_id = o.id JOIN customers c ON o.customer_id = c.id WHERE c.city = '{city}' AND strftime('%Y-%m', p.paid_at) = '{month}'",
                ["join", "date", "money"],
            ))
    for cat in _CATEGORIES:
        for month in _MONTHS:
            cn = _MONTH_CN[month]
            out.append((
                f"{cat}品类在{cn}的成交金额是多少？",
                f"SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id JOIN categories c ON p.category_id = c.id WHERE c.name = '{cat}' AND strftime('%Y-%m', o.order_date) = '{month}'",
                ["join", "date", "money", "jargon"],
            ))

    for year in ("2024", "2025"):
        out.append((
            f"注册于 {year} 年的客户有多少个？",
            f"SELECT COUNT(*) FROM customers WHERE strftime('%Y', signup_date) = '{year}'",
            ["date"],
        ))

    out.append(("沉默客户有多少个？", "SELECT COUNT(*) FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)", ["jargon", "subquery"]))
    out.append(("各订单状态的订单数量分布是怎样的？", "SELECT status, COUNT(*) FROM orders GROUP BY status", ["group"]))
    out.append(("每个品类的商品平均售价分别是多少？", "SELECT c.name, AVG(p.price) FROM products p JOIN categories c ON p.category_id = c.id GROUP BY c.id", ["group"]))
    out.append(("全部已完成订单的成交金额是多少？", "SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE o.status = 'completed'", ["money", "jargon"]))
    out.append(("平均每笔订单包含多少件商品？", "SELECT AVG(cnt) FROM (SELECT SUM(quantity) AS cnt FROM order_items GROUP BY order_id)", ["subquery"]))
    return out


def generate(
    db_path: str | Path = DEMO_DB_PATH,
    out_dir: str | Path = "eval/cases",
    seed: int = SEED,
) -> dict:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"演示库不存在: {db_path}（先运行 make demo-db）")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    valid, dropped = [], []
    try:
        for question, gold_sql, tags in _templates():
            try:
                rows = conn.execute(gold_sql).fetchmany(1)
            except sqlite3.Error as e:
                dropped.append(f"{question} → SQL 错误: {e}")
                continue
            if not rows or all(v is None for v in rows[0]):
                dropped.append(f"{question} → 空结果")
                continue
            valid.append({"question": question, "gold_sql": gold_sql, "tags": tags})
    finally:
        conn.close()

    rng = random.Random(seed)
    rng.shuffle(valid)
    for i, case in enumerate(valid, start=1):
        case["id"] = f"biz-{i:04d}"
    split_at = int(len(valid) * DEV_RATIO)
    dev, holdout = valid[:split_at], valid[split_at:]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, cases in (("business-dev", dev), ("business-holdout", holdout)):
        path = out_dir / f"{name}.jsonl"
        header = (
            f"# 自建业务评测集 {name}：{len(cases)} 条（seed={seed}，70/30 切分，gold 逐条执行校验）\n"
            "# ⚠️ holdout 只用于最终复核，调 prompt/检索期间绝不允许跑\n"
        )
        ordered = [
            {"id": c["id"], "question": c["question"], "gold_sql": c["gold_sql"], "tags": c["tags"]}
            for c in cases
        ]
        path.write_text(
            header + "\n".join(json.dumps(c, ensure_ascii=False) for c in ordered) + "\n",
            encoding="utf-8",
        )
        files[name] = str(path)
    return {"total": len(valid), "dev": len(dev), "holdout": len(holdout), "dropped": dropped, "files": files}


if __name__ == "__main__":
    info = generate()
    print(f"共 {info['total']} 条（dev {info['dev']} / holdout {info['holdout']}），已写入 {info['files']}")
    for d in info["dropped"]:
        print(f"  [剔除] {d}")
