"""FastAPI 服务：SSE 流式接口 + 单文件演示页 + Prometheus 指标 + 结果缓存。

    insight-agent serve            # 或 uvicorn "insight_agent.server:create_app" --factory

接口：
    GET  /                     演示网页（无前端框架，单文件）
    GET  /api/ask?question=…&chart=0|1   SSE：逐节点进度 + 最终结果
    GET  /charts/{name}        沙箱生成的图表文件
    GET  /metrics              Prometheus 指标
    GET  /healthz
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .agent import InsightAgent, RunOutcome
from .cache import BaseCache, build_cache, cache_key
from .config import Settings, get_settings

# ---------- Prometheus 指标 ----------

REQUESTS = Counter("insight_requests_total", "请求总数（按结果状态）", ["status"])
CACHE_HITS = Counter("insight_cache_hits_total", "结果缓存命中数")
HALLUCINATION_BLOCKED = Counter("insight_hallucination_blocked_total", "防幻觉拦截次数")
LATENCY = Histogram(
    "insight_request_seconds",
    "单次提问端到端延迟",
    buckets=(0.5, 1, 2, 4, 8, 16, 32, 64),
)
TOKENS = Counter("insight_llm_tokens_total", "累计 LLM token 消耗")
COST = Counter("insight_llm_cost_total", "累计 LLM 成本（按 .env 单价折算）")

_CHART_NAME = re.compile(r"^chart-[0-9a-f]{12}\.png$")

_NODE_LABELS = {
    "generate_sql": "生成 SQL",
    "execute": "守卫校验并执行",
    "repair": "自动修复",
    "chart": "生成图表（沙箱）",
    "summarize": "归纳回答",
    "fallback": "降级收尾",
}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _node_event(node: str, delta: dict) -> dict:
    payload: dict = {"node": node, "label": _NODE_LABELS.get(node, node)}
    attempts = delta.get("attempts")
    if node == "execute" and attempts:
        last = attempts[-1]
        payload["ok"] = last.ok
        if not last.ok:
            payload["error_kind"] = last.error_kind
            payload["error_message"] = (last.error_message or "")[:300]
    if node == "chart":
        payload["ok"] = bool(delta.get("chart_path"))
        if delta.get("chart_error"):
            payload["error_message"] = delta["chart_error"]
    return payload


def _outcome_payload(outcome: RunOutcome, cached: bool = False) -> dict:
    result = outcome.result
    return {
        "status": outcome.status,
        "cached": cached,
        "answer": outcome.answer,
        "sql": outcome.final_sql,
        "predicted_sql": outcome.predicted_sql,
        "columns": result.columns if result else [],
        "rows": [list(r) for r in result.rows[:50]] if result else [],
        "row_count": result.row_count if result else 0,
        "attempts": [
            {
                "sql": a.sql_raw,
                "ok": a.ok,
                "error_kind": a.error_kind,
                "error_message": (a.error_message or "")[:300] or None,
            }
            for a in outcome.attempts
        ],
        "selected_tables": outcome.selected_tables,
        "hallucination_blocked": outcome.hallucination_blocked,
        "chart_url": f"/charts/{Path(outcome.chart_path).name}" if outcome.chart_path else None,
        "chart_error": outcome.chart_error,
        "usage": outcome.usage,
        "latency_ms": outcome.latency_ms,
    }


def create_app(agent: InsightAgent | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    cache: BaseCache = build_cache(settings)
    app = FastAPI(title="insight-agent", docs_url=None, redoc_url=None)
    state = {"agent": agent}

    def get_agent() -> InsightAgent:
        if state["agent"] is None:  # 惰性构建：测试可注入，生产首个请求时组装
            from . import build_agent

            state["agent"] = build_agent(settings)
        return state["agent"]

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "cache": cache.backend, "mock": settings.llm_mock}

    @app.get("/metrics")
    def metrics():
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/charts/{name}")
    def chart_file(name: str):
        if not _CHART_NAME.match(name):  # 防路径穿越：只放行沙箱命名的文件
            raise HTTPException(status_code=404)
        path = Path(settings.chart_out_dir) / name
        if not path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/png")

    @app.get("/api/ask")
    def api_ask(
        question: str = Query(..., min_length=1, max_length=2000),
        chart: bool = Query(False),
        user: str = Query("default", max_length=64),
    ):
        agent_ = get_agent()
        key = cache_key(
            f"{user}|{question}",
            db_path=settings.db_path,
            model=agent_.llm.model_name,
            chart=chart,
        )

        def stream():
            start = time.monotonic()
            cached = cache.get(key)
            if cached is not None:
                CACHE_HITS.inc()
                REQUESTS.labels(status=cached.get("status", "ok")).inc()
                cached_payload = dict(cached)
                cached_payload["cached"] = True
                yield _sse("final", cached_payload)
                return
            outcome: RunOutcome | None = None
            for kind, item, extra in agent_.ask_stream(question, generate_chart=chart, user_id=user):
                if kind == "node":
                    yield _sse("node", _node_event(item, extra or {}))
                else:
                    outcome = item
            assert outcome is not None
            payload = _outcome_payload(outcome)
            REQUESTS.labels(status=outcome.status).inc()
            LATENCY.observe(time.monotonic() - start)
            TOKENS.inc(outcome.usage.get("total_tokens", 0))
            COST.inc(outcome.usage.get("cost", 0.0))
            if outcome.hallucination_blocked:
                HALLUCINATION_BLOCKED.inc()
            if outcome.succeeded:
                cache.set(key, payload)
            yield _sse("final", payload)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/", response_class=HTMLResponse)
    def index():
        return PAGE

    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings=settings), host=settings.server_host, port=settings.server_port)


# ---------- 单文件演示页（零前端依赖） ----------

PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>insight-agent</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 880px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.3rem; }
  #bar { display: flex; gap: .5rem; }
  #q { flex: 1; padding: .6rem .8rem; font-size: 1rem; border: 1px solid #8884; border-radius: 8px; }
  button { padding: .6rem 1.2rem; border: 0; border-radius: 8px; background: #2563eb; color: #fff; font-size: 1rem; cursor: pointer; }
  button:disabled { opacity: .5; }
  label { font-size: .9rem; align-self: center; user-select: none; }
  #steps { margin: 1rem 0 0; padding: 0; list-style: none; font-size: .9rem; opacity: .85; }
  #steps li { padding: .15rem 0; }
  pre { background: #8881; padding: .8rem; border-radius: 8px; overflow-x: auto; }
  table { border-collapse: collapse; margin: .8rem 0; font-size: .9rem; }
  th, td { border: 1px solid #8884; padding: .3rem .6rem; text-align: left; }
  #answer { background: #22c55e18; border-left: 3px solid #22c55e; padding: .8rem; border-radius: 0 8px 8px 0; white-space: pre-wrap; }
  #chart img { max-width: 100%; border-radius: 8px; margin-top: .8rem; }
  footer { margin-top: 1rem; font-size: .8rem; opacity: .6; }
  .err { color: #dc2626; }
</style>
</head>
<body>
<h1>insight-agent · 用自然语言查数据</h1>
<div id="bar">
  <input id="q" placeholder="例如：支付总金额最高的前3个城市是哪几个？" />
  <label><input type="checkbox" id="chart"> 图表</label>
  <button id="go">提问</button>
</div>
<ul id="steps"></ul>
<div id="out"></div>
<footer id="usage"></footer>
<script>
const $ = (id) => document.getElementById(id);
let es = null;
function esc(s) { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; }
$("go").onclick = run;
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
function run() {
  const q = $("q").value.trim();
  if (!q) return;
  if (es) es.close();
  $("steps").innerHTML = ""; $("out").innerHTML = ""; $("usage").textContent = "";
  $("go").disabled = true;
  const url = `/api/ask?question=${encodeURIComponent(q)}&chart=${$("chart").checked ? 1 : 0}`;
  es = new EventSource(url);
  es.addEventListener("node", (e) => {
    const d = JSON.parse(e.data);
    const li = document.createElement("li");
    li.innerHTML = d.ok === false
      ? `⚠️ ${esc(d.label)} — <span class="err">${esc(d.error_kind || "")} ${esc(d.error_message || "")}</span>`
      : `✅ ${esc(d.label)}`;
    $("steps").appendChild(li);
  });
  es.addEventListener("final", (e) => {
    const d = JSON.parse(e.data);
    let html = "";
    if (d.sql) html += `<h3>SQL${d.cached ? "（缓存命中）" : ""}</h3><pre>${esc(d.sql)}</pre>`;
    if (d.columns.length) {
      html += "<table><tr>" + d.columns.map(c => `<th>${esc(c)}</th>`).join("") + "</tr>";
      html += d.rows.map(r => "<tr>" + r.map(v => `<td>${esc(v === null ? "NULL" : String(v))}</td>`).join("") + "</tr>").join("");
      html += "</table>";
      if (d.row_count > d.rows.length) html += `<p>共 ${d.row_count} 行，仅展示前 ${d.rows.length} 行</p>`;
    }
    if (d.answer) html += `<div id="answer">${esc(d.answer)}</div>`;
    if (d.chart_url) html += `<div id="chart"><img src="${esc(d.chart_url)}" alt="chart"></div>`;
    if (d.chart_error) html += `<p class="err">图表生成失败：${esc(d.chart_error)}</p>`;
    $("out").innerHTML = html;
    const u = d.usage || {};
    $("usage").textContent = `状态 ${d.status} · LLM 调用 ${u.llm_calls ?? 0} 次 · tokens ${u.total_tokens ?? 0} · 成本 ${(u.cost ?? 0).toFixed(6)} · 耗时 ${d.latency_ms} ms` + (d.hallucination_blocked ? " · ⚠️ 防幻觉拦截已触发" : "");
    es.close(); $("go").disabled = false;
  });
  es.onerror = () => { es.close(); $("go").disabled = false; };
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
