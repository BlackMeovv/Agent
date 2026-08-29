# deepquery

**给业务人员的临时取数助手**：企业里大量长尾问题（"上周华东退货率怎么高了？"）不在任何
仪表盘上，现状是提数工单排队等分析师写 SQL。deepquery 让不会 SQL 的人一句话拿到数——
自动完成 **选表 → 生成 SQL → 安全执行 → 出错自纠 → 给出结论**，每个回答可追溯到 SQL 与
原始结果；自带执行准确率（EX）评测闭环、预算熔断与成本记账。演示库为电商场景（客户/订单/
商品/支付），架构与库解耦，可接任意 SQLite/MySQL/PostgreSQL（只读账号）。

```
用户提问 → [LangGraph 状态机]
             ├─ schema_rag     混合检索选表（BM25 + 可选向量，RRF 融合）+ 业务字典/例句注入
             ├─ generate_sql   基于检索出的 schema 上下文生成 SQL
             ├─ execute        sqlglot AST 守卫 → 只读执行（超时/行数限额）
             ├─ repair         手写 Reason-Act-Observe 修复循环（按错误类型定向提示 + 重复检测）
             ├─ summarize      基于查询结果作答 → 防幻觉校验：每个数字必须有出处，
             │                 违规先重写一次、仍失败则降级为确定性结果预览
             └─ fallback       轮次/预算耗尽时的无 LLM 降级收尾
```

## 评测结果（实测，全部可复现）

| 评测集 | 配置 | EX（95% CI） | 说明 |
|---|---|---|---|
| 业务集 dev · 165 题 ×3 | baseline | 93.3% [90.8, 95.2] | 失败模式分析 → 定向修复 |
| 业务集 dev · 165 题 ×3 | 口径注入 + 输出纪律 | **97.8% [96.1, 98.8]** | 按题配对翻转 5:0（零回归） |
| 业务集 holdout · 71 题 ×3（密封） | 同上 | **97.7% [94.6, 99.0]** | 提升无过拟合 |
| BIRD dev · 150 题固定子集 | 全量 schema 直供 | **64.7% [56.7, 71.9]** | 参照：BIRD 论文 GPT-4 基线 46.4% |
| BIRD dev · 150 题固定子集 | 检索选表（RAG） | 61.3% [53.3, 68.8] | 选表召回 95.5%；消融结论：上下文装得下时直供更优 → auto 判据据此改为按 schema 体积 |

复现：`make business LABEL=x` / `make bird ROOT=... LABEL=x`（模型走任意 OpenAI 兼容接口）。
每次跑分的完整 JSON 与对比报告在 [eval/results/](eval/results/)，
失败案例逐条复盘（含根因验证与修复前后对比）见 [docs/badcases.md](docs/badcases.md)。

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

# 6. 起服务（SSE 流式网页 http://localhost:8000 + /metrics）
make serve

# 或者 docker compose 一键起全套（服务+Redis+Prometheus+Grafana 大盘）
docker compose up --build
```

## 接入你自己的数据库

agent 与具体数据库**完全解耦**：schema 是连接时运行时自省的（建表语句+注释+样例行），
守卫按所连引擎的方言解析、提示词按方言渲染、检索索引由所连的库派生，
没有任何针对演示库的硬编码。支持三种引擎，换库只需改一个连接目标：

```bash
deepquery ask "问题" --db /path/to/your.sqlite                        # SQLite 文件
deepquery ask "问题" --db mysql://readonly:pwd@host:3306/yourdb       # MySQL（uv sync --extra mysql）
deepquery ask "问题" --db postgres://readonly:pwd@host:5432/yourdb    # PostgreSQL（--extra postgres）
# 或在 .env 里改 DB_PATH，服务/CLI 全部跟随
```

服务器引擎的只读纵深：AST 守卫（第一道）+ 会话级只读与语句超时（第二道，
MySQL `SET SESSION TRANSACTION READ ONLY` / PG `default_transaction_read_only`）+
**只读数据库账号（硬边界，生产接入的部署要求）**。本地验证：

```bash
make db-dumps && docker compose -f docker-compose.dbs.yml up -d   # 一键起带演示数据的 MySQL+PG
deepquery ask "上海的客户一共有多少个？" --db mysql://readonly:readonly@localhost:3306/deepquery
```

内置电商演示库只是让仓库开箱即跑的样例数据；跑 BIRD 基准时 agent 会在
几十个从未见过的第三方库上逐题切换（`--db-root`），这本身就是泛化能力的证明。

## 前端（Vue3）

`web/` 是正式前端：Vue 3 + Vite + Pinia，Organic 暖色设计（对话流 + 回答逐字流式 +
运行过程检查器 + 库表结构/记忆/历史侧栏，亮/暗主题，字体自托管不依赖外网）。

```bash
cd web && npm install
npm run dev      # 开发：http://localhost:5173（已配好代理到后端 8000）
npm run build    # 构建后，后端检测到 web/dist 会自动作为主页托管（内置页移至 /legacy）
```

## 其他入口

```bash
# MCP server：接入 Claude Desktop / Claude Code 等任意 MCP 客户端
uv sync --extra mcp && uv run deepquery-mcp

# 跨会话记忆：记住你的口径偏好（按用户隔离）
deepquery remember "我说的销售额一律指已完成订单的成交金额"
deepquery ask "这个月销售额多少？" --chart    # --chart 生成沙箱图表

# 压测（服务端先用 LLM_MOCK=1 起，测工程链路吞吐，不花模型钱）
locust -f eval/load/locustfile.py --host http://localhost:8000
```

不配置 API 也可以完整验证工程链路：

```bash
make test        # 271 个离线测试：守卫/只读层/评测打分/图编排/服务端（MockLLM）
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

## 文档

- [部署指南](docs/DEPLOY.md)：服务器部署（docker compose、nginx SSE 反代、访问口令、安全边界）
- [评测基准](docs/benchmarks.md)：BIRD/Spider 接入方法与统计口径
- [失败案例复盘](docs/badcases.md)：逐条根因验证与修复前后对比
- [前端契约](docs/frontend-spec.md)：SSE 事件与 API 约定
