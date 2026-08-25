# insight-agent

An enterprise data-analysis agent: ask questions in natural language, get guarded SQL,
self-repaired execution, sandboxed charts, and verified answers — with a reproducible
execution-accuracy eval harness built in.

[中文文档 / Chinese README](README.md)

```
question → [LangGraph state machine]
             ├─ schema_rag   hybrid retrieval (BM25 + optional embeddings, RRF-fused)
             │               + glossary / few-shot / per-user memory injection
             ├─ generate_sql schema-grounded SQL generation
             ├─ execute      sqlglot AST guard → read-only execution (timeout, row cap)
             ├─ repair       hand-written reason-act-observe loop with error-kind-specific
             │               hints, duplicate-SQL detection, budget circuit breaker
             ├─ chart        model-written matplotlib code run in a locked-down sandbox
             ├─ summarize    answer generation → every number must be traceable to the
             │               query result, or the answer is rewritten / degraded
             └─ fallback     deterministic wrap-up when rounds/budget are exhausted
```

## Features

- **Database-agnostic**: schema is introspected at connection time; point `DB_PATH`
  (or `--db`) at any SQLite file. BIRD evaluation runs the agent across dozens of
  unseen third-party databases.
- **Eval harness first**: BIRD/Spider adapters with seeded, validated subsets; a
  236-case in-house business set (dev/holdout split); execution accuracy with Wilson
  95% CIs over repeated runs; McNemar significance between configs; an offline
  gold-replay self-check that must score 100%; regression CI on every commit.
- **Defense in depth**: AST-level SQL guard (single SELECT, table allowlist, forced
  LIMIT) + triple read-only SQLite layer + chart-code sandbox (no network, memory/CPU
  limits) + static deny-list.
- **Hallucination gate**: numbers in answers are matched against query results
  (thousands separators, percents, CJK units, rounded forms); violations trigger one
  rewrite, then a deterministic fallback.
- **Production surface**: FastAPI + SSE streaming web demo, Redis result cache,
  Langfuse tracing with per-run cost accounting, Prometheus/Grafana dashboard,
  locust load-test profile, one-command docker compose, an MCP server for Claude
  Desktop/Code, and per-user cross-session preference memory.

## Quick start

```bash
make install && make demo-db
cp .env.example .env        # any OpenAI-compatible API (DeepSeek / Qwen / OpenAI / Ollama)
make ask Q="Which 3 cities have the highest total payments?"
make smoke                  # 20-case smoke eval: accuracy / cost / latency
make serve                  # SSE web demo at http://localhost:8000
docker compose up --build   # full stack: app + Redis + Prometheus + Grafana
```

Everything except the LLM calls runs offline: `make test` (250+ tests, no API key)
and `make smoke-gold` (harness self-check) must always be green.
