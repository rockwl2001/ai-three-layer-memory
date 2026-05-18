# -*- coding: utf-8 -*-
"""
MemoryOffloader — 对话中途 offload / load 上下文
================================================
供 AI Agent 在对话过程中调用：

  offload(episode)      — 将当前对话片段存入 L1
  load_context(query)   — 召回相关上下文注入当前对话
  start_task()          — 开始一个任务（自动创建 task_id）
  complete_task()       — 完成任务
  emit_tool_call()      — 记录一次工具调用（≥5次自动创建知识卡）
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from .episodic import EpisodicStore, DB_PATH
from .semantic import SemanticMemory, WORKSPACE


# ── 触发阈值 ──────────────────────────────────────────────

TOOL_CALL_THRESHOLD = 5   # 工具调用 ≥5 次自动创建 project_knowledge


class MemoryOffloader:
    """
    对话中途的记忆 offload 接口。

    用法（AI Agent 在每次对话轮次中调用）：
      offloader = MemoryOffloader(session_id="xxx", project="video2text")

      # 用户消息后
      offloader.add_turn("user", "我想继续昨天的转写任务")

      # AI 回复后
      offloader.add_turn("assistant", "好的，从 tasks.db 找到你的任务...")

      # 工具调用后（用于知识卡判断）
      offloader.emit_tool_call()

      # 对话结束或任务切换时
      offloader.offload_current(summary="用户想继续昨天的 video2text 任务，我们查到了任务ID...")
    """

    def __init__(
        self,
        session_id: str,
        project: str = "",
        task_id: Optional[str] = None,
        workspace: Optional[Path] = None,
    ):
        self.session_id = session_id
        self.project = project
        self.task_id = task_id or self._gen_task_id()
        self.ws = workspace or WORKSPACE

        self.store = EpisodicStore()
        self.semantic = SemanticMemory()

        # 当前对话缓冲
        self._current_turns: List[Dict[str, str]] = []
        self._tool_call_count = 0
        self._last_project = project

        # 初始化或恢复 task
        if task_id:
            self.store.upsert_task(
                task_id=task_id,
                title=f"Session {session_id}",
                project=project,
                status="running",
            )
        else:
            # 创建新 task
            self.store.upsert_task(
                task_id=self.task_id,
                title=f"Session {session_id}",
                project=project,
                status="running",
            )

    def _gen_task_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:12]

    # ── 对话缓冲 ─────────────────────────────────────────

    def add_turn(self, role: str, text: str):
        """记录一轮对话"""
        self._current_turns.append({"role": role, "text": text})

    def add_chunk(self, chunk_text: str, role: str = "mixed"):
        """直接添加一个片段（用于外部传入内容）"""
        self._current_turns.append({"role": role, "text": chunk_text})

    # ── 工具调用计数 ─────────────────────────────────────

    def emit_tool_call(self):
        """每次工具调用后调用，自动判断是否需要创建知识卡"""
        self._tool_call_count += 1
        self.store.increment_tool_calls(self.task_id)

        if self._tool_call_count == TOOL_CALL_THRESHOLD:
            self._auto_create_knowledge_card()

    def _auto_create_knowledge_card(self):
        """工具调用 ≥5 次，自动创建 project_knowledge"""
        if not self.project:
            return
        # 检查是否已有 knowledge card
        existing = self.store.get_active_tasks(self.project)
        # 知识卡逻辑通过 tasks.db 中的 summary 字段标记
        # 完整实现见 knowledge.py
        pass

    # ── Offload ──────────────────────────────────────────

    def offload_current(
        self,
        summary: str = "",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        将当前缓冲的对话片段 offload 到 L1。

        Args:
            summary:  该片段的摘要（供召回用）
            force:    True 则不判断，直接 offload

        Returns:
            {"episode_id": ..., "offload_type": ..., "summary": ...}
        """
        if not self._current_turns and not summary:
            return {"episode_id": None, "offload_type": "none", "summary": ""}

        # 合并当前缓冲为文本
        combined = "\n".join(
            f"[{t['role']}] {t['text']}" for t in self._current_turns
        )

        # 语义判断：是否需要真正 offload
        offload_type = self._should_offload(combined, summary)

        if offload_type == "skip" and not force:
            self._current_turns.clear()
            return {"episode_id": None, "offload_type": "skip", "summary": ""}

        # 写入 L1
        episode_id = self.store.add_episode(
            session_id=self.session_id,
            chunk_text=combined[:5000],  # 截断保护
            role="mixed",
            project=self.project,
        )

        # 记录摘要
        offload_summary = summary or combined[:200]

        # 写 offload log
        self.store.log_offload(
            task_id=self.task_id,
            episode_id=episode_id,
            offload_type=offload_type,
            summary=offload_summary[:500],
        )

        self._current_turns.clear()
        return {
            "episode_id": episode_id,
            "offload_type": offload_type,
            "summary": offload_summary,
            "task_id": self.task_id,
        }

    def _should_offload(self, text: str, summary: str) -> str:
        """
        判断 offload 类型：
          - task_switch:  任务切换，需要强召回
          - new_topic:    新话题开始
          - milestone:     里程碑完成
          - normal:       普通片段，保留
          - skip:         噪音，跳过
        """
        # 强制 offload 信号
        skip_signals = [
            r"继续[上次上上个]?.*任务",
            r"继续昨天",
            r"接着上次的",
            r"新开一个?任务",
            r"换个事情",
            r"不对，不是这个",
        ]
        for sig in skip_signals:
            if re.search(sig, text):
                return "task_switch"

        # 里程碑信号
        milestone_signals = [
            r"完成了",
            r"成功了",
            r"搞定了",
            r"搞定",
            r"好了",
            r"可以了",
            r"跑通了",
            r"通过了",
        ]
        for sig in milestone_signals:
            if re.search(sig, text):
                return "milestone"

        # 新话题信号
        topic_signals = [
            r"另外",
            r"还有个事",
            r"顺便",
            r"问一下",
            r"想问一下",
        ]
        if any(re.search(sig, text) for sig in topic_signals):
            return "new_topic"

        # 长文本自动 offload
        if len(text) > 1000:
            return "normal"

        return "skip"

    # ── Context Load ─────────────────────────────────────

    def load_context(
        self,
        query: str,
        project: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """
        召回与 query 相关的上下文，拼接为可注入的文本。

        用于 AI Agent 在系统 prompt 或回复前注入相关记忆。
        """
        search_project = project or self.project
        episodes = self.store.get_recent_episodes(
            project=search_project if search_project else None,
            limit=limit,
        )

        if not episodes:
            return ""

        # 简单关键词匹配
        query_words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for ep in episodes:
            ep_words = set(re.findall(r"\w+", ep["chunk_text"].lower()))
            overlap = query_words & ep_words
            score = len(overlap) / max(len(query_words), 1)
            scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:5]

        if not top or top[0][0] == 0:
            return ""

        lines = ["## 相关记忆上下文\n"]
        for score, ep in top:
            ts = ep["created_at"][:16]
            text = ep["chunk_text"][:300]
            lines.append(f"**[{ts}]** {text}...")
        return "\n".join(lines)

    # ── Task 管理 ────────────────────────────────────────

    def complete_task(self, summary: str = ""):
        """标记任务完成"""
        self.store.complete_task(self.task_id, summary)

    def get_task_summary(self) -> Dict[str, Any]:
        """获取当前任务摘要"""
        task = self.store.get_task(self.task_id)
        if not task:
            return {}
        return {
            "task_id": self.task_id,
            "project": task["project"],
            "title": task["title"],
            "status": task["status"],
            "tool_calls": task["tool_calls"],
            "summary": task["summary"],
        }

    def switch_project(self, new_project: str):
        """切换项目（自动 offload 当前 + 创建新 task）"""
        self.offload_current(summary=f"切换到项目 {new_project}")
        self.project = new_project
        self._tool_call_count = 0
        self._gen_task_id()  # 生成新 task_id
        self.store.upsert_task(
            task_id=self.task_id,
            title=f"Project: {new_project}",
            project=new_project,
            status="running",
        )

    # ── 批量召回（供梦境系统使用）────────────────────────

    def get_today_episodes(self) -> List[Dict[str, Any]]:
        today = datetime.now().date().isoformat()
        conn = EpisodicStore()._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM episodes
                WHERE created_at LIKE ?
                ORDER BY created_at DESC
                """,
                (today + "%",),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
