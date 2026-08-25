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

（跑完第一轮真实评测后开始填写）
