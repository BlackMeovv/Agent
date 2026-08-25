# Agent 开发岗简历项目：市场调研报告

> 调研时间：2026-08-25。基于 6 路并行网络调研（国内 JD、海外 JD、技术趋势、开源竞争格局、面试官视角、上岸案例），共 160+ 次真实检索。来源清单见文末。

## 一、结论摘要（TL;DR）

1. **市场在爆发，但供需已略反转**：2025 年国内 AI 岗位月均新发职位同比增长 74.1%（BOSS直聘），但人才供需比已到 1.08-1.11——"有真实落地项目"成为区分度关键，而不是"会调 API"。
2. **岗位考察重心是工程化，不是算法**：JD 不卷论文，考察"把 LLM 落地为产品"的能力。高频关键词：Python、LangGraph/LangChain、RAG、Function Calling、**MCP（2026 年已写进一线大厂 JD 正文）**、Multi-Agent、Memory、向量数据库、FastAPI/Docker。
3. **三类项目已"烂大街"，做了等于没做**：智能客服、基础 RAG 知识库问答、LoRA 微调提点（面试官原话："十个有八个的项目描述长得一模一样"）。另外通用 Manus 复刻、通用 coding agent 的开源赛道也已饱和。
4. **拉开差距的公式**：垂直场景 + 1-2 个做深的工程难点 + **可量化的评测闭环**。海外多方信源一致认为"eval 设计是辨别真实 LLM 经验的单一最佳信号"。
5. **校招窗口真实存在**：Epoch AI 分析 1604 份中国 AI 公司 JD，平均只要求 1.6 年经验（美国 5.5 年），校园岗占工程岗近 20%；字节 2026 校招 5000+ 岗位中 90% 与 AI 相关。校招策略：聚焦 2-3 个有深度的项目，讲清难点与效果。

## 二、国内 JD 要求什么

### 技能关键词（按出现频率）

| 层次 | 关键词 |
|---|---|
| 语言 | Python（绝对主导），Go/Java 为辅 |
| 框架 | LangChain、LangGraph、LlamaIndex、Dify、AutoGen、CrewAI、Coze |
| 概念 | RAG、Prompt Engineering、Function Calling、**MCP**、Multi-Agent、ReAct/Plan-and-Execute、Memory 机制、向量数据库（Milvus/Chroma/FAISS） |
| 工程 | FastAPI/Flask、Docker/K8s、Redis/MySQL、消息队列、SSE 流式输出 |
| 进阶（偏算法岗） | LoRA/QLoRA 微调、vLLM 推理部署、量化（应用岗只需"了解"） |

### 典型 JD 原文（真实岗位）

- **腾讯混元 Agent 开发工程师**："开发多 Agent 协作系统，实现任务规划、工具调用及智能体间的通信机制"；加分项："有 Agent 实战落地经验的优先"、"参与过开源项目贡献经验的优先"。
- **字节 Aime Agent 工程师**："上下文组装与压缩、Memory 机制（短期/长期/情景记忆）、调度机制"、"Skill 框架设计、插件化生态"。校招侧"不限技术栈"，强调自驱 + AI 热情。
- **上海金融科技（25-30K）**："Agent 项目 0-1 完整落地经验"、基于 LangGraph 搭建生产级工作流（ReAct、Multi-Agent、MCP、A2A）、端到端 RAG 流水线（文档解析、混合检索 BM25+向量、重排）。
- **北京 Agent 架构岗（45-60K）**："JSON Schema + Function Calling 结构化输出控制"；加分项：LLM 输出质量自动化评测体系；**投递须附 GitHub 主页链接**。

### 校招 vs 社招

- 社招：3 年+ 经验、强调"生产级""端到端落地"、指定框架精通程度。
- 校招：拔高学历（硕士、985/211 优先，但非绝对），放低经验门槛；百度校招只要求"掌握一门语言 + 对 AI/LLM 有浓厚兴趣，愿意深入学习 Agent、RAG"。
- 薪资参考：2026 届大厂 AI 校招年薪普遍 35-45 万，顶尖 50 万+。

## 三、海外岗位与评估方式（面试形态的风向标）

- Anthropic Applied AI JD 核心技能清单：高级 prompt engineering、agent 开发、**评估框架（evaluation frameworks）**、transcript 分析、MCP、规模化部署。
- Sierra 的 take-home 最具代表性：**禁用框架，直接用 API 手写 tool calling 构建客服 agent**，考察产品判断和架构取舍——说明"只会框架 API、不懂 agent loop 本身"会露馅。
- OpenAI FDE 系统设计轮专考 token 经济学、eval gates、模型非确定性。
- 杀手级面试题（KORE1 2026 招聘指南）："你上一个 agent **单次调用成本**是多少？"——生产工程师会脱口而出具体数字（如 $0.04）。
- 雇主红旗清单：简历罗列所有框架 = 只做过原型；从不提 trajectory evals / ground truth / 回归集 = 没做过生产；说不出可观测性工具 = 没调试过失败轨迹。

## 四、技术趋势（2025-2026）

1. **框架收敛**：LangGraph 是生产部署最多的框架（v1.0，约 400 家公司生产使用：Klarna/Uber/LinkedIn/JPMorgan）；AutoGen 已进维护模式（并入 Microsoft Agent Framework）；OpenAI 可视化 Agent Builder 下线——**"低代码拖拽退潮、代码优先胜出"**；Claude Agent SDK 是增速最快的新入口。
2. **MCP 已成事实标准**：官方 registry 近万 server、SDK 月下载约 9700 万、41% 受访组织已在生产使用。A2A 存在但量级远小于 MCP。
3. **热点能力方向**：coding agents（最大商业化方向）、browser/computer use、deep research、**memory（Mem0/Zep/Letta 成独立赛道，benchmark 刚起步）**、**sandboxing（E2B/Firecracker microVM 成为"agent 执行层"）**。
4. **Observability/Evals**：Langfuse（开源，被 ClickHouse 收购）、LangSmith、Braintrust、Arize Phoenix；OpenTelemetry GenAI 语义约定成为可移植标准。2026 最佳实践是**"trace 与 eval 闭环"**：生产 trace 沉淀为评测集，eval 结果回流监控。
5. **生产级 vs Demo 级的差距共识**：错误恢复与优雅降级、可观测性、guardrails 与人工升级路径、成本可控、确定性编排（可靠性放编排层而非 prompt 里）、eval 与真实表现的落差。

## 五、开源格局：哪里饱和、哪里有空间

**饱和（不要做）**：通用自主 agent（AutoGPT 18.7 万星、OpenManus 5.6 万星）、通用 coding agent（Cline/opencode/gemini-cli 十余个高星）、基础 RAG 问答、"workflow 编排 + 聊天界面"伪 agent。

**有空间（个人 2-3 个月可及）**：
- Agent 评估与可观测性（公认 gap）
- 记忆与上下文工程（2026 新爆发：claude-mem、headroom 等均为新项目）
- 垂直领域 agent（strix 渗透测试 5.8 万星、DeepTutor 教辅 3.7 万星证明垂直可行）
- Agent Skills 生态（发布 5 周出现 7.1 万个 skills，个人开发者主导）

**个人爆火案例的共同规律**：单点极致 + 时机 + 零门槛安装 + 人人看得懂的 demo。
- browser-use：两名 ETH 学生，把"agent 操作浏览器"收敛成一个 pip 即装即用的库，3 个月 5 万星进 YC。
- ai-hedge-fund（6.3 万星）：一人项目，投资大师 persona 多智能体辩论——把多智能体用在人人都懂的领域（钱）。
- gpt-researcher：看到 AutoGPT 死循环，只解决一个任务（在线深度研究），成为品类先驱。

## 六、面试官怎么审项目

**追问模式是"逐层下钻"**：用了什么框架 → 为什么选它 → 它的劣势 → 你怎么优化的——"追到挖到你真正做过的地方才停"。

**高频追问（要提前准备答案）**：
- Agent 最常见的失败场景（工具调用失败/上下文溢出/目标漂移）怎么解决？
- 工具调用超时怎么设计重试/熔断/降级？
- 完成判断与终止条件怎么设计，避免死循环/过早结束？
- MCP 和 Function Calling 的区别？为什么不直接让模型生成脚本执行？
- RAG 的 Chunk 怎么切、效果不好怎么排查？
- **"ReAct 实际效果如何？"——要答数据**（如"准确率提升约 15%"），只背概念被判浅。
- 你怎么证明一次 prompt/模型/检索配置调整带来了改善？（评测集 + 回归）

**被判"调 API demo"的红旗**：只罗列功能不讲踩坑；堆框架名说不出选型理由；无评测词汇；token 成本盲区。

**工程题占大头**（牛客 80 道 Agent 面试题）：流式输出（SSE vs WebSocket、断点续传、点击停止立即释放资源）、高并发（排队削峰、熔断切备用模型、幂等）、安全（Prompt Injection 防御、**SQL/代码执行沙箱与权限隔离**、灾备切换）。

**基础四大块**：Transformer 原理（attention/KV cache/采样参数）、RAG 全链路、Agent 设计模式（ReAct/Reflection/记忆/终止条件/LangGraph State-Node-Edge）、medium 算法题。

**系统设计高频题**：企业知识库问答（必刷）、**NL2SQL Agent（重点问 SQL 注入与权限风险）**、客服多 Agent、Deep Research、代码解释器沙箱。

## 七、上岸案例给出的模板

- **成功公式**："RAG/Agent + 具体业务场景 + 可量化评估"三件套。
  - 自学者 Gustaf 的 CondoGPT（房产数据对话平台，LangChain/LangGraph + FAISS + 只读数据库 + SQL 注入防护）→ 首份 AI 工程师 offer。
  - 转行者做"自动部署代码库的 Agent"，简历附 demo、主投初创 → 北京初创大模型岗，薪资比后端 offer 高近 30%。
- **简历写法对照**（牛客热帖）：
  - ❌ 失败写法："基于 Spring Boot + Vue + DeepSeek 实现智能知识库问答系统"
  - ✅ 成功写法："构建 200+ 条 RAG 离线测评集，多轮对比实验将 Top5 命中率由 X% 提升至 Y%"
- **结构**：业务痛点 → 技术方案 → 量化结果（准确率/延迟/成本数字）+ 自建评测集与 bad case 分析。
- **权重排序**：真实实习/业务落地 > 有评估数据的自建项目 > 高质量开源与博客 > Kaggle/黑客松（除非高排名）。
- **反面教材**：无评估数据的项目"价值大减"；应用岗简历投向基座/训练/Infra 岗是典型方向错配。

## 八、对本项目的直接启示

理想简历项目 = 一个**完整可运行**的垂直场景 Agent 系统，覆盖：

- [ ] RAG 链路（解析/切片/混合检索/重排）
- [ ] Function Calling + MCP 工具调用（含失败重试/兜底）
- [ ] Multi-Agent 编排（LangGraph）+ 明确的终止条件设计
- [ ] Memory 机制（至少会话内，最好跨会话）
- [ ] 沙箱与权限隔离（代码/SQL 执行）
- [ ] **评测闭环：公开基准跑分 + 自建评测集 + 回归测试 + bad case 分析**
- [ ] 可观测性（Langfuse/OTel 追踪 + token 成本记账，能报出单次调用成本）
- [ ] 部署（FastAPI + SSE 流式 + Docker）
- [ ] 开源化（英文 README、demo、可复现脚本）

---

### 主要信息来源（节选）

- 国内 JD：腾讯混元/字节 Aime/淘天/阿里云校招 JD、V2EX 实招帖、掘金 50+ JD 分析、Epoch AI 1604 份中国 AI 公司 JD 分析（智源社区转载）
- 市场数据：BOSS直聘 2025 AI 岗位报告、脉脉 2025 人才报告
- 海外：Anthropic/OpenAI/Sierra/Cognition/Cursor 招聘页与面经（Greenhouse、HeroHunt、KORE1 2026 招聘指南、dev.to AI Engineer Interview Playbook）
- 技术趋势：LangChain/LangGraph v1.0 发布、MCP registry 统计、Microsoft Agent Framework GA 公告、OpenTelemetry GenAI 语义约定、Langfuse/ClickHouse 收购报道
- 开源格局：GitHub API 星数实测（2026-08-25）
- 面经：牛客 80 道 Agent 面试题、SegmentFault 2026 Agent 岗面试复盘、kamacoder/JavaGuide 大模型面经、Hamel Husain evals 系列
