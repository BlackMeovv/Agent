.PHONY: install demo-db test smoke smoke-gold ask schema

install:            ## 安装依赖（含 dev）
	uv sync --extra dev

demo-db:            ## 生成确定性演示库
	uv run python -m insight_agent.demo_data

test:               ## 离线测试（不需要 API Key）
	uv run pytest

smoke-gold:         ## 离线自检评测基建：gold 回放必须 100%
	uv run python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl --gold-replay

smoke:              ## 真实 LLM 跑冒烟评测（需要 .env）
	uv run python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl

ask:                ## 提问：make ask Q="上海的客户一共有多少个？"
	uv run insight-agent ask "$(Q)" --trace

schema:             ## 查看喂给模型的 schema 上下文
	uv run insight-agent schema
