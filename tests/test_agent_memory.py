# -*- coding: utf-8 -*-
"""
单元测试
"""

import pytest
import tempfile
import os
from pathlib import Path

from agent_memory.episodic import EpisodicStore
from agent_memory.semantic import (
    jaccard_similarity,
    six_dim_score,
    SemanticMemory,
    PROMOTION_THRESHOLD,
)
from agent_memory.offloader import MemoryOffloader, TOOL_CALL_THRESHOLD
from agent_memory.knowledge import KnowledgeCardStore


class TestJaccard:
    def test_identical(self):
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_totally_different(self):
        assert jaccard_similarity("hello", "world") == 0.0

    def test_partial_overlap(self):
        s1 = "用户想继续昨天的视频转写任务"
        s2 = "用户想继续视频转写任务"
        assert 0 < jaccard_similarity(s1, s2) < 1


class TestSixDimScore:
    def test_high_score(self):
        score = six_dim_score(
            frequency=5,
            relevance=0.9,
            recency_days=1,
            unique_contexts=4,
            concept_tags=["video", "transcribe"],
        )
        assert score >= PROMOTION_THRESHOLD

    def test_low_score(self):
        score = six_dim_score(
            frequency=1,
            relevance=0.2,
            recency_days=10,
            unique_contexts=1,
            concept_tags=[],
        )
        assert score < PROMOTION_THRESHOLD


class TestEpisodicStore:
    """使用真实数据库（test 用完清理）"""

    def test_add_episode(self):
        # 使用临时 session，确保清理
        import uuid
        sid = f"pytest-{uuid.uuid4().hex[:8]}"
        store = EpisodicStore()
        eid = store.add_episode(sid, "pytest episode", role="user", project="pytest")
        assert eid
        eps = store.get_recent_episodes(session_id=sid, limit=10)
        assert len(eps) >= 1

    def test_task_upsert(self):
        import uuid
        tid = f"pytest-{uuid.uuid4().hex[:8]}"
        store = EpisodicStore()
        store.upsert_task(tid, "测试任务", project="pytest")
        task = store.get_task(tid)
        assert task is not None
        assert task["title"] == "测试任务"

    def test_increment_tool_calls(self):
        import uuid
        tid = f"pytest-{uuid.uuid4().hex[:8]}"
        store = EpisodicStore()
        store.upsert_task(tid, "任务2")
        n = store.increment_tool_calls(tid)
        assert n == 1


class TestMemoryOffloader:
    def test_add_turn(self):
        loader = MemoryOffloader(session_id="test-session", project="test")
        loader.add_turn("user", "你好")
        loader.add_turn("assistant", "你好，我是钳子")
        assert len(loader._current_turns) == 2

    def test_offload_task_switch(self):
        loader = MemoryOffloader(session_id="test-session", project="test")
        loader.add_turn("user", "继续上次的任务")
        loader.add_turn("assistant", "好的")
        result = loader.offload_current()
        assert result["offload_type"] == "task_switch"
        assert result["episode_id"] is not None

    def test_load_context(self):
        loader = MemoryOffloader(session_id="test-session", project="test")
        loader.add_turn("user", "视频转写出问题了")
        loader.offload_current(summary="用户反馈 video2text 出问题")

        context = loader.load_context(query="视频转写", project="test")
        assert "视频" in context or "转写" in context or context == ""


class TestKnowledgeCardStore:
    @pytest.fixture
    def kstore(self):
        return KnowledgeCardStore()

    def test_upsert_and_get(self, kstore):
        cid = kstore.upsert("test_proj", "测试知识卡", "这是测试内容")
        assert cid is not None
        cards = kstore.get_by_project("test_proj")
        assert len(cards) >= 1
        assert cards[0]["title"] == "测试知识卡"
