"""只读数据库工具：第二道防线。

三重保护，任何一层失效都不可写：
1. URI mode=ro 打开（文件级只读）
2. PRAGMA query_only=ON
3. sqlite authorizer 只放行 SELECT/READ/FUNCTION

超时：sqlite 没有单查询超时，用 progress_handler 在截止时间后中断，
表现为 OperationalError("interrupted")，归类为 timeout。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .contract import QueryResult

_ALLOWED_AUTH_OPS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    # 子查询/CTE 会临时物化，需要允许（仍受 mode=ro 与 query_only 约束）
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


class ReadOnlyDatabase:
    def __init__(self, db_path: str | Path, timeout_seconds: float = 15, max_rows: int = 200):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"数据库不存在: {self.db_path}（演示库请先运行 `make demo-db` 生成）"
            )
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")

        def authorizer(action, arg1, arg2, db_name, trigger):
            if action in _ALLOWED_AUTH_OPS:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        conn.set_authorizer(authorizer)
        return conn

    # ---------- schema ----------

    def table_names(self) -> list[str]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def schema_by_table(self, sample_rows: int = 3, max_cell: int = 60) -> dict[str, str]:
        """逐表的 schema 上下文：建表 DDL + 少量样例行（值格式很关键）。

        按表拆开是 Schema RAG 的基础——大库场景下只把检索命中的表喂给模型。
        样例单元格截断，防止 BIRD 这类库里的长文本撑爆上下文。
        """
        out: dict[str, str] = {}
        conn = self._connect()
        try:
            ddls = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for name, ddl in ddls:
                parts = [f"{ddl.strip()};"]
                if sample_rows > 0:
                    cur = conn.execute(f'SELECT * FROM "{name}" LIMIT {int(sample_rows)}')
                    cols = [d[0] for d in cur.description]
                    lines = [", ".join(cols)]
                    for row in cur.fetchall():
                        cells = []
                        for v in row:
                            text = "NULL" if v is None else str(v)
                            cells.append(text[:max_cell] + "…" if len(text) > max_cell else text)
                        lines.append(", ".join(cells))
                    sample = "\n--   ".join(lines)
                    parts.append(f"-- {name} 样例行:\n--   {sample}")
                out[name] = "\n".join(parts)
        finally:
            conn.close()
        return out

    def schema_text(self, sample_rows: int = 3) -> str:
        """全量 schema 上下文（小库直接全喂；大库走 Schema RAG 选表）。"""
        return "\n\n".join(self.schema_by_table(sample_rows).values())

    # ---------- query ----------

    def run_query(self, sql: str) -> QueryResult:
        """执行已通过守卫的 SQL。错误结构化分类，永不抛业务异常。"""
        start = time.monotonic()
        deadline = start + self.timeout_seconds
        conn = self._connect()
        try:
            # progress handler：每执行一批 VM 指令检查一次截止时间
            conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(self.max_rows + 1)
            truncated = len(rows) > self.max_rows
            rows = rows[: self.max_rows]
            latency_ms = int((time.monotonic() - start) * 1000)
            if not rows:
                return QueryResult(
                    ok=False,
                    columns=columns,
                    latency_ms=latency_ms,
                    error_kind="empty_result",
                    error_message="查询执行成功但返回 0 行",
                )
            return QueryResult(
                ok=True,
                columns=columns,
                rows=[tuple(r) for r in rows],
                row_count=len(rows),
                truncated=truncated,
                latency_ms=latency_ms,
            )
        except sqlite3.Error as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return QueryResult(
                ok=False,
                latency_ms=latency_ms,
                error_kind=_classify_sqlite_error(e),
                error_message=str(e),
            )
        finally:
            conn.close()


def _classify_sqlite_error(e: sqlite3.Error) -> str:
    msg = str(e).lower()
    if "interrupted" in msg:
        return "timeout"
    if "no such table" in msg:
        return "no_such_table"
    if "no such column" in msg:
        return "no_such_column"
    if "syntax error" in msg:
        return "syntax_error"
    if "not authorized" in msg or "readonly" in msg or "read-only" in msg or "query_only" in msg:
        return "guard_rejected"
    return "execution_error"
