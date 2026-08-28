# 公开基准接入：BIRD / Spider

评测数字的可信度来自公开基准——别人可以下载同样的数据、跑同样的子集来复现你的结果。
本项目用 **执行准确率（EX）** 作为主指标，与 BIRD/Spider 官方口径一致（比结果集，不比 SQL 文本）。

## 1. 下载数据（在你自己的机器上）

**BIRD dev**（推荐主基准，更接近真实业务库）：
- 官网 https://bird-bench.github.io/ → 下载 dev set（`dev.zip`，约 1-2 GB，含 `dev.json` 与 `dev_databases/`）
- 解压到任意目录，如 `~/data/bird_dev/`

**Spider 1.0 dev**（补充基准，题目更"教科书"）：
- 官网 https://yale-lily.github.io/spider → 下载 spider.zip（含 `dev.json` 与 `database/`）
- 解压到如 `~/data/spider/`

## 2. 转换为评测子集（固定 seed，可复现）

```bash
make bird-prepare ROOT=~/data/bird_dev      # 抽 150 条，gold 逐条执行校验，坏 gold 剔除
make spider-prepare ROOT=~/data/spider
```

生成 `eval/cases/bird-dev.jsonl`：每条带 `db` 字段（相对 ROOT 的库路径）。
**子集文件要提交进 git**——这是"评测集固定化"的一部分，别人拿到仓库就能复现同一子集。

## 3. 跑分

```bash
# baseline（3 次重复，汇总为 Wilson 95% 置信区间）
make bird ROOT=~/data/bird_dev LABEL=baseline

# 每做一个优化跑一次，label 换成配置名
make bird ROOT=~/data/bird_dev LABEL=schema-rag
```

成本参考：150 条 × 3 次重复 ≈ 450 次调用；按 DeepSeek 价格每次全流程约 0.002-0.01 元，
一轮全量约 1-5 元。日常改动跑 `make smoke`（20 条演示库冒烟集）即可，全量留给里程碑。

## 4. 汇总消融表

```bash
make report FILES="eval/results/bird-dev-baseline-*.json eval/results/bird-dev-schema-rag-*.json"
# 或加配对显著性检验：
uv run python -m deepquery.evalkit.report <baseline.json> <optimized.json> --mcnemar
```

输出 markdown 表：每行一个配置，EX 带置信区间 + 成本 + 延迟。
McNemar 检验回答"这次提升是真的还是抖动"——面试聊到这里就赢了。

## 约定

- 调 prompt / 检索只看 dev 子集；最终简历数字用另抽的 held-out 子集复核（换个 seed 再 prepare 一份，标记为 holdout，平时绝不跑）。
- 报告 JSON 全部留档在 `eval/results/`（已 gitignore，重要结果手动挑进 git 或写进 report.md）。
