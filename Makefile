.PHONY: install demo-db test smoke smoke-gold ask schema bird-prepare spider-prepare bird report

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

bird-prepare:       ## 转换 BIRD dev 子集：make bird-prepare ROOT=~/data/bird_dev
	uv run python -m insight_agent.evalkit.prepare bird $(ROOT) --out eval/cases/bird-dev.jsonl --limit 150

spider-prepare:     ## 转换 Spider dev 子集：make spider-prepare ROOT=~/data/spider
	uv run python -m insight_agent.evalkit.prepare spider $(ROOT) --out eval/cases/spider-dev.jsonl --limit 150

bird:               ## BIRD 跑分：make bird ROOT=~/data/bird_dev LABEL=baseline
	uv run python -m insight_agent.evalkit.runner --cases eval/cases/bird-dev.jsonl --db-root $(ROOT) --repeats 3 --label $(LABEL)

report:             ## 消融对比表：make report FILES="eval/results/a.json eval/results/b.json"
	uv run python -m insight_agent.evalkit.report $(FILES) --out eval/results/report.md

business-set:       ## 重新生成自建业务评测集（dev/holdout）
	uv run python -m insight_agent.evalkit.business_set

business:           ## 业务集跑分：make business LABEL=baseline
	uv run python -m insight_agent.evalkit.runner --cases eval/cases/business-dev.jsonl --repeats 3 --label $(LABEL)

serve:              ## 启动服务（网页 http://localhost:8000）
	uv run insight-agent serve
