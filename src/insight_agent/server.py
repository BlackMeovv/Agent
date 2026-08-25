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
        db_target = settings.db_path
        if "://" in db_target:  # 连接串脱敏：只露引擎与库名
            scheme, rest = db_target.split("://", 1)
            db_target = f"{scheme}://…/{rest.rsplit('/', 1)[-1]}"
        else:
            db_target = Path(db_target).name
        return {
            "ok": True,
            "cache": cache.backend,
            "mock": settings.llm_mock,
            "db": db_target,
            "model": "mock" if settings.llm_mock else settings.llm_model,
        }

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
<title>InsightAgent · 数据查询台</title>
<style>
  :root {
    --bg: #f7f8fa; --panel: #ffffff; --text: #1d2129; --muted: #86909c;
    --border: #e5e6eb; --border-strong: #c9cdd4;
    --accent: #165dff; --accent-hover: #0e4bd6;
    --ok: #00b42a; --err: #f53f3f; --warn: #ff7d00;
    --log-bg: #fbfcfd;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17171a; --panel: #1e1f24; --text: #e6e8ea; --muted: #7d8592;
      --border: #313339; --border-strong: #46484f;
      --accent: #3c7eff; --accent-hover: #5a91ff;
      --ok: #27c346; --err: #f76965; --warn: #ff9626;
      --log-bg: #191a1e;
    }
  }
  * { box-sizing: border-box; margin: 0; }
  html, body { height: 100%; }
  body {
    background: var(--bg); color: var(--text); font-size: 13px; line-height: 1.6;
    font-family: -apple-system, "SF Pro Text", "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif;
  }
  .mono { font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; }

  /* 顶栏 */
  .topbar {
    display: flex; align-items: center; gap: 16px; height: 44px; padding: 0 16px;
    background: var(--panel); border-bottom: 1px solid var(--border);
  }
  .brand { font-size: 14px; font-weight: 600; letter-spacing: .01em; }
  .brand span { color: var(--accent); }
  .topbar .env {
    margin-left: auto; display: flex; gap: 14px; color: var(--muted); font-size: 12px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
  }
  .env b { color: var(--text); font-weight: 500; }

  .main { max-width: 1080px; margin: 0 auto; padding: 16px; }

  /* 查询区 */
  .querybox { background: var(--panel); border: 1px solid var(--border); border-radius: 3px; }
  .querybox .row { display: flex; gap: 8px; padding: 10px; }
  #q {
    flex: 1; padding: 7px 10px; font-size: 13px; color: var(--text); background: var(--bg);
    border: 1px solid var(--border-strong); border-radius: 2px; outline: none;
  }
  #q:focus { border-color: var(--accent); }
  button.primary {
    padding: 7px 18px; font-size: 13px; border: 1px solid var(--accent); border-radius: 2px;
    background: var(--accent); color: #fff; cursor: pointer;
  }
  button.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  button.primary:disabled { opacity: .5; cursor: default; }
  .opt { display: flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px;
    white-space: nowrap; cursor: pointer; user-select: none; }
  .opt input { accent-color: var(--accent); }
  .samples { border-top: 1px solid var(--border); padding: 6px 10px; color: var(--muted); font-size: 12px; }
  .samples a { color: var(--muted); text-decoration: none; margin-right: 14px; cursor: pointer; }
  .samples a:hover { color: var(--accent); text-decoration: underline; }

  /* 分区 */
  section.block { background: var(--panel); border: 1px solid var(--border); border-radius: 3px; margin-top: 12px; }
  .block-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 12px; border-bottom: 1px solid var(--border);
    font-size: 12px; font-weight: 600; color: var(--text);
  }
  .block-head .sub { color: var(--muted); font-weight: 400; }
  .block-body { padding: 0; }

  /* 执行日志 */
  #log {
    list-style: none; padding: 8px 0; background: var(--log-bg);
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
  }
  #log li { display: flex; gap: 10px; padding: 2px 12px; color: var(--muted); }
  #log .t { color: var(--muted); flex-shrink: 0; }
  #log .lv { width: 42px; flex-shrink: 0; font-weight: 600; }
  #log .ok .lv { color: var(--ok); }
  #log .bad .lv { color: var(--err); }
  #log .run .lv { color: var(--accent); }

  /* SQL */
  pre.sql {
    padding: 10px 12px; overflow-x: auto; font-size: 12.5px; line-height: 1.7;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
  }
  .ghost {
    font-size: 12px; padding: 2px 8px; border: 1px solid var(--border-strong); border-radius: 2px;
    background: transparent; color: var(--muted); cursor: pointer;
  }
  .ghost:hover { color: var(--accent); border-color: var(--accent); }

  /* 结果表 */
  .tblwrap { overflow: auto; max-height: 420px; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  th {
    position: sticky; top: 0; background: var(--bg); color: var(--muted); font-weight: 500;
    text-align: left; padding: 6px 12px; border-bottom: 1px solid var(--border-strong); white-space: nowrap;
  }
  td { padding: 5px 12px; border-bottom: 1px solid var(--border); white-space: nowrap;
    font-variant-numeric: tabular-nums; }
  td.num, th.num { text-align: right; font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; }
  td.idx { color: var(--muted); font-size: 11px; text-align: right; width: 1%; }
  tbody tr:hover td { background: color-mix(in srgb, var(--accent) 6%, transparent); }
  td i { color: var(--muted); }

  /* 回答 */
  .answer { padding: 10px 12px; white-space: pre-wrap; font-size: 13px; }
  #chartimg { display: block; max-width: 100%; padding: 10px 12px; }

  /* 状态条 */
  .statusbar {
    margin-top: 12px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 3px;
    background: var(--panel); color: var(--muted); font-size: 12px;
    font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    display: flex; gap: 16px; flex-wrap: wrap;
  }
  .statusbar b { color: var(--text); font-weight: 500; }
  .flag-warn { color: var(--warn); }
  .flag-ok { color: var(--ok); }
  .hidden { display: none !important; }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">Insight<span>Agent</span> <span style="color:var(--muted);font-weight:400;font-size:12px">数据查询台</span></div>
  <div class="env" id="env"></div>
</div>

<div class="main">
  <div class="querybox">
    <div class="row">
      <input id="q" placeholder="输入业务问题，例如：支付总金额最高的前3个城市是哪几个？" autocomplete="off">
      <label class="opt"><input type="checkbox" id="chart">生成图表</label>
      <button class="primary" id="go">查 询</button>
    </div>
    <div class="samples" id="samples">示例：</div>
  </div>

  <section class="block hidden" id="logblock">
    <div class="block-head">执行日志</div>
    <ol id="log"></ol>
  </section>

  <section class="block hidden" id="sqlblock">
    <div class="block-head"><span>SQL <span class="sub" id="sqlnote"></span></span><button class="ghost" id="copy">复制</button></div>
    <pre class="sql"><code id="sql"></code></pre>
  </section>

  <section class="block hidden" id="datablock">
    <div class="block-head"><span>查询结果 <span class="sub" id="rowcount"></span></span></div>
    <div class="tblwrap"><table id="tbl"></table></div>
  </section>

  <section class="block hidden" id="ansblock">
    <div class="block-head">回答</div>
    <div class="answer" id="answer"></div>
  </section>

  <section class="block hidden" id="chartblock">
    <div class="block-head">图表</div>
    <img id="chartimg" alt="chart">
  </section>

  <div class="statusbar hidden" id="statusbar"></div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const EXAMPLES = [
  "支付总金额最高的前3个城市是哪几个？",
  "各品类的成交金额分别是多少？",
  "下单次数最多的前5名客户是谁？",
  "2025年上半年每个月的支付总金额是多少？",
];
let es = null, t0 = 0;

function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
function ts() { return ((performance.now() - t0) / 1000).toFixed(2) + "s"; }

fetch("/healthz").then(r => r.json()).then(h => {
  $("env").innerHTML =
    `db <b>${esc(h.db || "-")}</b>` +
    `model <b>${esc(h.model || "-")}</b>` +
    `cache <b>${esc(h.cache)}</b>` +
    (h.mock ? `<span style="color:var(--warn)">MOCK</span>` : "");
}).catch(() => {});

EXAMPLES.forEach(text => {
  const a = document.createElement("a");
  a.textContent = text;
  a.onclick = () => { $("q").value = text; run(); };
  $("samples").appendChild(a);
});

$("go").onclick = run;
$("q").addEventListener("keydown", e => { if (e.key === "Enter") run(); });
$("copy").onclick = () => {
  navigator.clipboard.writeText($("sql").textContent).then(() => {
    $("copy").textContent = "已复制"; setTimeout(() => $("copy").textContent = "复制", 1200);
  });
};

function makeRow(cls, level, text) {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.innerHTML = `<span class="t">${ts()}</span><span class="lv">${level}</span><span>${esc(text)}</span>`;
  return li;
}

function isNumCol(rows, i) {
  return rows.length > 0 && rows.every(r => r[i] === null || typeof r[i] === "number");
}

function run() {
  const q = $("q").value.trim();
  if (!q) return;
  if (es) es.close();
  ["sqlblock", "datablock", "ansblock", "chartblock", "statusbar"].forEach(id => $(id).classList.add("hidden"));
  $("log").innerHTML = "";
  $("logblock").classList.remove("hidden");
  $("go").disabled = true;
  t0 = performance.now();
  $("log").appendChild(makeRow("run", "RUN", `question=${JSON.stringify(q)}`));
  const pending = makeRow("run", "…", "等待下一步");
  $("log").appendChild(pending);

  es = new EventSource(`/api/ask?question=${encodeURIComponent(q)}&chart=${$("chart").checked ? 1 : 0}`);

  es.addEventListener("node", (e) => {
    const d = JSON.parse(e.data);
    const bad = d.ok === false;
    const detail = bad ? `${d.label} — ${d.error_kind || ""} ${d.error_message || ""}` : d.label;
    $("log").insertBefore(makeRow(bad ? "bad" : "ok", bad ? "ERR" : "OK", detail), pending);
  });

  es.addEventListener("final", (e) => {
    const d = JSON.parse(e.data);
    pending.remove();
    $("log").appendChild(
      makeRow(d.status.startsWith("ok") ? "ok" : "bad", "DONE", `status=${d.status} latency=${d.latency_ms}ms`)
    );

    if (d.sql) {
      $("sql").textContent = d.sql;
      $("sqlnote").textContent = d.cached ? "（缓存命中，未消耗模型调用）" : "";
      $("sqlblock").classList.remove("hidden");
    }
    if (d.columns && d.columns.length) {
      const numCols = d.columns.map((_, i) => isNumCol(d.rows, i));
      let html = "<thead><tr><th class='idx'>#</th>" +
        d.columns.map((c, i) => `<th${numCols[i] ? ' class="num"' : ""}>${esc(c)}</th>`).join("") + "</tr></thead><tbody>";
      html += d.rows.map((r, ri) => `<tr><td class="idx">${ri + 1}</td>` +
        r.map((v, i) => `<td${numCols[i] ? ' class="num"' : ""}>${v === null ? "<i>NULL</i>" : esc(v)}</td>`).join("") + "</tr>").join("");
      $("tbl").innerHTML = html + "</tbody>";
      $("rowcount").textContent = d.row_count > d.rows.length
        ? `共 ${d.row_count} 行，展示前 ${d.rows.length} 行` : `${d.row_count} 行`;
      $("datablock").classList.remove("hidden");
    }
    if (d.answer) { $("answer").textContent = d.answer; $("ansblock").classList.remove("hidden"); }
    if (d.chart_url) { $("chartimg").src = d.chart_url; $("chartblock").classList.remove("hidden"); }

    const u = d.usage || {};
    let bar = `status=<b>${esc(d.status)}</b>` +
      `<span>llm_calls=<b>${u.llm_calls ?? 0}</b></span>` +
      `<span>tokens=<b>${u.total_tokens ?? 0}</b></span>` +
      `<span>cost=<b>${(u.cost ?? 0).toFixed(6)}</b></span>` +
      `<span>latency=<b>${d.latency_ms}ms</b></span>` +
      `<span>cache=<b>${d.cached ? "hit" : "miss"}</b></span>`;
    if (d.selected_tables) bar += `<span>tables=<b>${esc(d.selected_tables.join(","))}</b></span>`;
    if (d.hallucination_blocked) bar += `<span class="flag-warn">hallucination_blocked=true</span>`;
    if (d.chart_error) bar += `<span class="flag-warn">chart_error=${esc(d.chart_error)}</span>`;
    $("statusbar").innerHTML = bar;
    $("statusbar").classList.remove("hidden");
    es.close(); $("go").disabled = false;
  });

  es.onerror = () => {
    pending.remove();
    $("log").appendChild(makeRow("bad", "ERR", "连接中断"));
    es.close(); $("go").disabled = false;
  };
}

const params = new URLSearchParams(location.search);
if (params.get("q")) { $("q").value = params.get("q"); if (params.get("chart") === "1") $("chart").checked = true; run(); }
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
