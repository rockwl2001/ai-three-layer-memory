# -*- coding: utf-8 -*-
"""
L1 情景记忆层 — SQLite 存储
=============================
存储高精度的情景单元：
  - 对话片段（session + 片段文本 + 时间戳 + 项目标签）
  - 任务快照（task_id + 状态 + 关键产出摘要）
  - 上下文卸载记录（offload 日志，供梦境系统参考）
"""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple


DB_PATH = Path(__file__).parent.parent / "episodes.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            project     TEXT DEFAULT '',
            chunk_text  TEXT NOT NULL,
            role        TEXT DEFAULT 'user',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            is_archived INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
        CREATE INDEX IF NOT EXISTS idx_episodes_project  ON episodes(project);
        CREATE INDEX IF NOT EXISTS idx_episodes_created  ON episodes(created_at DESC);

        CREATE TABLE IF NOT EXISTS tasks (
            task_id     TEXT PRIMARY KEY,
            project     TEXT DEFAULT '',
            title       TEXT NOT NULL,
            status      TEXT DEFAULT 'running',
            summary     TEXT DEFAULT '',
            tool_calls  INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project);
        CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status);

        CREATE TABLE IF NOT EXISTS offload_log (
            id          TEXT PRIMARY KEY,
            task_id     TEXT,
            episode_id  TEXT,
            offload_type TEXT NOT NULL,
            summary     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_summaries (
            id          TEXT PRIMARY KEY,
            date        TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            score       REAL DEFAULT 0.0,
            created_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summaries(date DESC);
        """)
        conn.commit()
    finally:
        conn.close()


class EpisodicStore:
    """L1 情景记忆存储"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return get_conn()

    # ── Episodes ────────────────────────────────────────────

    def add_episode(
        self,
        session_id: str,
        chunk_text: str,
        role: str = "user",
        project: str = "",
    ) -> str:
        """写入一个情景片段，返回 episode_id"""
        episode_id = str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO episodes (id,session_id,project,chunk_text,role,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (episode_id, session_id, project, chunk_text, role, now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return episode_id

    def get_recent_episodes(
        self,
        session_id: Optional[str] = None,
        project: Optional[str] = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查询最近的片段"""
        conn = self._conn()
        try:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT * FROM episodes
                    WHERE session_id=? AND is_archived=0
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            elif project:
                rows = conn.execute(
                    """
                    SELECT * FROM episodes
                    WHERE project=? AND is_archived=0
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (project, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM episodes
                    WHERE is_archived=0
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def archive_episodes(self, episode_ids: List[str]):
        conn = self._conn()
        try:
            placeholders = ",".join("?" * len(episode_ids))
            conn.execute(
                f"UPDATE episodes SET is_archived=1 WHERE id IN ({placeholders})",
                episode_ids,
            )
            conn.commit()
        finally:
            conn.close()

    # ── Tasks ──────────────────────────────────────────────

    def upsert_task(
        self,
        task_id: str,
        title: str,
        project: str = "",
        status: str = "running",
        summary: str = "",
        tool_calls: int = 0,
    ) -> bool:
        now = datetime.now().isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO tasks (task_id,project,title,status,summary,tool_calls,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    summary=excluded.summary,
                    tool_calls=excluded.tool_calls,
                    updated_at=excluded.updated_at
                """,
                (task_id, project, title, status, summary, tool_calls, now, now),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def increment_tool_calls(self, task_id: str) -> int:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE tasks SET tool_calls=tool_calls+1 WHERE task_id=?",
                (task_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT tool_calls FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            return row["tool_calls"] if row else 0
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_active_tasks(self, project: str = "") -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            if project:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status='running' AND project=? ORDER BY updated_at DESC",
                    (project,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status='running' ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def complete_task(self, task_id: str, summary: str = ""):
        conn = self._conn()
        try:
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE tasks SET status='completed', summary=?, updated_at=? WHERE task_id=?",
                (summary, now, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Offload Log ────────────────────────────────────────

    def log_offload(
        self,
        task_id: str,
        episode_id: str,
        offload_type: str,
        summary: str,
    ) -> str:
        log_id = str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO offload_log (id,task_id,episode_id,offload_type,summary,created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (log_id, task_id, episode_id, offload_type, summary, now),
            )
            conn.commit()
        finally:
            conn.close()
        return log_id

    def get_offload_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM offload_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Daily Summaries ───────────────────────────────────

    def save_daily_summary(
        self, date_str: str, role: str, content: str, score: float = 0.0
    ) -> str:
        summary_id = str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO daily_summaries (id,date,role,content,score,created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (summary_id, date_str, role, content, score, now),
            )
            conn.commit()
        finally:
            conn.close()
        return summary_id

    def get_daily_summaries(self, date_str: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM daily_summaries WHERE date=? ORDER BY score DESC",
                (date_str,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── 搜索 ─────────────────────────────────────────────

    def search_episodes(self, keyword: str, limit: int = 30) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            pattern = f"%{keyword}%"
            rows = conn.execute(
                """
                SELECT * FROM episodes
                WHERE chunk_text LIKE ? AND is_archived=0
                ORDER BY created_at DESC LIMIT ?
                """,
                (pattern, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_session_episodes(self, session_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM episodes
                WHERE session_id=? AND is_archived=0
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# 初始化
init_db()
