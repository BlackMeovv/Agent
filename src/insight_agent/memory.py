"""跨会话记忆：按用户存"口径偏好"，提问时检索相关条目注入上下文。

典型条目："我说的销售额一律指已完成订单的成交金额"、"默认只看 2025 年的数据"。
存 SQLite（重启不丢），检索用与业务字典相同的 BM25——记忆本质上就是
一份按用户隔离、随使用增长的私人业务字典。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .retrieval import BM25, tokenize


class MemoryStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def remember(self, user_id: str, note: str) -> int:
        note = note.strip()
        if not note:
            raise ValueError("记忆内容不能为空")
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (user_id, note, created_at) VALUES (?, ?, ?)",
                (user_id, note, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            return cursor.lastrowid

    def forget(self, user_id: str, note_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
            )
            return cursor.rowcount > 0

    def notes(self, user_id: str) -> list[tuple[int, str, str]]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, note, created_at FROM notes WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()

    def recall(self, user_id: str, question: str, top_n: int = 3) -> list[str]:
        """检索与问题相关的记忆；条目很少时（<= top_n）全部返回。"""
        rows = self.notes(user_id)
        if not rows:
            return []
        texts = [note for _id, note, _ts in rows]
        if len(texts) <= top_n:
            return texts
        bm25 = BM25([tokenize(t) for t in texts])
        scores = bm25.scores(tokenize(question))
        ranked = sorted(range(len(texts)), key=lambda i: -scores[i])
        return [texts[i] for i in ranked[:top_n] if scores[i] > 0]
