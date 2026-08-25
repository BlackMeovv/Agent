# insight-agent

企业数据分析 Agent：用自然语言查数据库。自动完成 **选表 → 生成 SQL → 安全执行 → 出错自纠 → 给出结论**，自带执行准确率（EX）评测闭环、预算熔断与成本记账。

```
用户提问 → [LangGraph 状态机]
             ├─ generate_sql   基于 schema 上下文生成 SQL
             ├─ execute        sqlglot AST 守卫 → 只读执行（超时/行数限额）
             ├─ repair         手写 Reason-Act-Observe 修复循环（结构化错误分类 + 重复检测）
             ├─ summarize      基于查询结果作答（不编造数字）
             └─ fallback       轮次/预算耗尽时的无 LLM 降级收尾
```

## 快速开始

```bash
# 1. 安装依赖（需要 uv：https://docs.astral.sh/uv/）
make install

# 2. 配置模型 API（任何 OpenAI 兼容接口：DeepSeek / Qwen / Kimi / OpenAI / 本地 Ollama）
cp .env.example .env   # 然后填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL

# 3. 生成演示库（确定性电商模拟库：客户/商品/订单/支付，6 张表）
make demo-db

# 4. 提问
make ask Q="下单次数最多的前5名客户是谁？"

# 5. 跑冒烟评测（20 题，报执行准确率/成本/延迟）
make smoke
```

不配置 API 也可以完整验证工程链路：

```bash
make test        # 116 个离线测试：守卫/只读层/评测打分/图编排（MockLLM）
make smoke-gold  # 评测基建自检：gold SQL 离线回放，必须 20/20
```

## 安全设计（纵深防御）

| 层 | 机制 |
|---|---|
| 第一道：SQL 守卫 | sqlglot AST 校验——只放行单条 SELECT、表白名单、拒绝系统表/跨库/表值函数，强制注入 `LIMIT` |
| 第二道：数据库层 | `mode=ro` 只读打开 + `PRAGMA query_only` + sqlite authorizer 三重锁死写操作 |
| 运行时 | 单查询超时中断、行数截断、单次提问 token/金额预算熔断 |

## 评测

- `eval/cases/smoke.jsonl`：20 条冒烟题（单表/连接/金额/多跳），每条带人工核验的 gold SQL
- **公开基准**：`make bird-prepare` / `make bird` 一键接入 BIRD/Spider dev（见 [docs/benchmarks.md](docs/benchmarks.md)），子集固定 seed 抽样、gold 逐条执行校验
- 指标：**执行准确率 EX**（与 BIRD/Spider 口径一致：比结果集不比 SQL 文本），
  `--repeats 3` 重复跑分汇总为 **Wilson 95% 置信区间**；配置间对比用 **McNemar 配对检验**（`make report`）
- 质量门禁：gold 必须过守卫、可执行、非空、自评满分（`tests/test_smoke_gold.py` 强制）；
  `--gold-replay` 离线回放不到 100% 即判定评测基建有 bug
- CI：每次提交自动跑全部离线测试 + 评测自检

## 可观测性

在 [Langfuse Cloud](https://cloud.langfuse.com)（免费版即可）建项目拿到两个 key 填进 `.env`，
再 `uv sync --extra trace`——之后每次提问的完整链路（每个节点的 SQL、错误分类、token、
成本、延迟）都能在 Langfuse 网页上图形化查看，不需要自己写任何前端。
未配置时追踪完全关闭，零开销。

## 项目文档

- [调研报告](docs/research.md)：为什么做这个方向（岗位 JD / 技术趋势 / 面试考察点调研）
- [项目方案](docs/plan.md)：架构设计、里程碑、评测方案

## Roadmap

- [x] Week 1：最小闭环（生成 → 守卫 → 执行 → 自纠错）+ 冒烟评测集 + 离线测试
- [x] Week 2：BIRD/Spider 基准接入、Langfuse 追踪、Wilson 置信区间 + McNemar 检验、消融对比报告
- [ ] Week 3：Schema RAG（混合检索选表）、按错误类型的修复策略、防幻觉数字校验
- [ ] Week 4：图表沙箱、FastAPI + SSE 流式服务、docker compose 一键部署
- [ ] Week 5+：MCP server、跨会话记忆、200+ 条业务评测集、压测与监控大盘、多模型横评
