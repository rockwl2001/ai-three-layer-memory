# -*- coding: utf-8 -*-
"""
L2 项目知识卡 — SQLite 存储
===========================
参考 Hermes Skills 思路，按项目聚类可复用的操作流程。

触发条件：某项目工具调用 ≥5 次 → 自动创建/更新知识卡

表：project_knowledge
  - id, project, title, content, trigger, state, updated_at
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from .episodic import EpisodicStore, get_conn


class KnowledgeCardStore:
    """项目知识卡存储"""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        conn = get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_knowledge (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project     TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    content     TEXT NOT NULL DEFAULT '',
                    trigger     TEXT DEFAULT '',
                    source_task_id TEXT DEFAULT '',
                    state       TEXT DEFAULT 'active',
                    updated_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_project
                    ON project_knowledge(project, state)
            """)
            conn.commit()
        finally:
            conn.close()

    def upsert(
        self,
        project: str,
        title: str,
        content: str,
        trigger: str = "",
        source_task_id: str = "",
        state: str = "active",
    ) -> int:
        """创建或更新知识卡"""
        now = datetime.now().isoformat()
        conn = get_conn()
        try:
            # 检查是否已存在同名知识卡
            existing = conn.execute(
                "SELECT id FROM project_knowledge WHERE project=? AND title=? AND state='active'",
                (project, title),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE project_knowledge
                    SET content=?, trigger=?, updated_at=?
                    WHERE id=?
                    """,
                    (content, trigger, now, existing["id"]),
                )
                conn.commit()
                return existing["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO project_knowledge
                        (project,title,content,trigger,source_task_id,state,updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (project, title, content, trigger, source_task_id, state, now),
                )
                conn.commit()
                return cursor.lastrowid
        finally:
            conn.close()

    def get_by_project(
        self, project: str, state: str = "active"
    ) -> List[Dict[str, Any]]:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM project_knowledge
                WHERE project=? AND state=?
                ORDER BY updated_at DESC
                """,
                (project, state),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_active_all(self) -> List[Dict[str, Any]]:
        conn = get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM project_knowledge
                WHERE state='active'
                ORDER BY project, updated_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def archive(self, card_id: int):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE project_knowledge SET state='archived', updated_at=? WHERE id=?",
                (datetime.now().isoformat(), card_id),
            )
            conn.commit()
        finally:
            conn.close()

    def merge_cards(self, project: str, cards: List[int], new_title: str):
        """
        合并多条知识卡为一条（参考 Hermes Curator Umbrella-building）。
        """
        if len(cards) < 2:
            return

        conn = get_conn()
        try:
            placeholders = ",".join("?" * len(cards))
            rows = conn.execute(
                f"SELECT content FROM project_knowledge WHERE id IN ({placeholders})",
                cards,
            ).fetchall()
            merged = "\n\n---\n\n".join(r["content"] for r in rows)

            # 更新第一条，删除其余
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE project_knowledge SET title=?, content=?, updated_at=? WHERE id=?",
                (new_title, merged, now, cards[0]),
            )
            for cid in cards[1:]:
                conn.execute(
                    "UPDATE project_knowledge SET state='archived', updated_at=? WHERE id=?",
                    (now, cid),
                )
            conn.commit()
        finally:
            conn.close()

    def delete(self, card_id: int):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM project_knowledge WHERE id=?", (card_id,))
            conn.commit()
        finally:
            conn.close()
