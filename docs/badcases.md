# Bad Case 复盘

> 记录纪律：每次评测跑完，把未通过的 case 按失败模式归类记在这里；
> 每类给出根因 → 对策 → 修复后的前后对比。这份文档是消融表之外最有说服力的
> 面试素材（"error analysis 是一切的地基" — Hamel Husain）。
> 例句库（eval/knowledge/examples.jsonl）里的 few-shot 只能从这里的人工修正产生。

## 失败模式分类

| 类别 | 判定特征 | 典型对策 |
|---|---|---|
| A. 选表错误 | table_recall < 1，SQL 用错表 | 表注释补充、检索 top_k 调整、业务字典补条目 |
| B. 口径理解错 | 表选对了但聚合/过滤口径错（如用目录价算成交额） | 业务字典补口径、few-shot 例句 |
| C. 过滤值写错 | empty_result 后修复失败（大小写/中英文/日期格式） | 样例行覆盖该列、repair 提示强化 |
| D. SQL 方言错 | syntax_error / execution_error（SQLite 不支持的语法） | 提示词方言约束、修复提示 |
| E. 幻觉列名/表名 | no_such_column / no_such_table 且修复失败 | schema 上下文排版、few-shot |
| F. 语义歧义 | SQL 合理但与 gold 口径不同（题目本身多解） | 修评测集题面，或标注可接受多解 |
| G. 结果比对误判 | 人工看结果等价但 EX 判错（列序/舍入/单位） | 修 scorer 规则并加回归测试 |

## 记录模板

```
### <case-id> · 类别 <A-G> · <日期>
- 问题：
- 预测 SQL：
- gold SQL：
- 根因（一句话）：
- 对策：
- 复验：修复后该 case 通过？同类 case 整体提升？（贴跑分数字）
```

---

### smoke-06 · 类别 F（兼有输出列冗余） · 2026-08-27
- 问题：每个商品品类下各有多少个商品？
- 预测 SQL：`SELECT c.id AS category_id, c.name, COUNT(p.id) FROM categories c LEFT JOIN products p ON p.category_id = c.id GROUP BY c.id, c.name ORDER BY c.id`
- gold SQL：`SELECT c.name, COUNT(*) FROM categories c JOIN products p ON p.category_id = c.id GROUP BY c.name`
- 根因（一句话）：模型多输出了一列 `category_id`（题目没要），且用 LEFT JOIN 把"零商品品类"也计为 0——两处口径都"合理但与题意不符"，EX 按列数直接判负。
- 对策：题面补明确输出要求（"给出品类名和商品数，两列"）；提示词强调"只返回题目要求的列"。值得注意：模型的 LEFT JOIN 语义上未必更差，是题目没说清。
- 复验：待修复后重跑。

### smoke-12 · 类别 F · 2026-08-27
- 问题：按销量（销售数量合计）最高的前5个商品是哪些？
- 预测 SQL：加了 `WHERE o.status IN ('completed','shipped')` 后再聚合
- gold SQL：不区分订单状态，直接对 order_items 聚合
- 根因（一句话）：口径分歧——"销量"是否应剔除已取消订单？模型选择了剔除（业务上完全站得住），gold 是全量口径；题目没有指明，两种解释都对。
- 对策：修题面，注明口径（"不区分订单状态"或"只算已完成/已发货"，任选其一写死）；同类含糊指标（销售额/毛利）的题面全部排查一遍。
- 复验：待修复后重跑。

（结论：首轮 smoke 90%（18/20），两条失败均为 F 类——评测集题面歧义，而非模型能力缺陷。
这正是 error analysis 的价值：第一轮就发现"该修的是题目，不是模型"。）
