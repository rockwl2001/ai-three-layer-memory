# -*- coding: utf-8 -*-
"""
工具函数单元测试（已重构为 agent_memory.semantic）
"""

import pytest

from agent_memory.semantic import jaccard_similarity, six_dim_score


class TestJaccard:
    def test_identical_strings(self):
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_totally_different(self):
        assert jaccard_similarity("hello", "world") == 0.0

    def test_partial_overlap(self):
        s1 = "用户想继续昨天的视频转写任务"
        s2 = "用户想继续视频转写任务"
        assert 0 < jaccard_similarity(s1, s2) < 1


class TestSixDimScore:
    def test_high_quality_entry(self):
        score = six_dim_score(
            frequency=5,
            relevance=0.9,
            recency_days=1,
            unique_contexts=4,
            concept_tags=["video", "transcribe", "task"],
        )
        assert score >= 0.75

    def test_low_quality_entry(self):
        score = six_dim_score(
            frequency=1,
            relevance=0.2,
            recency_days=10,
            unique_contexts=1,
            concept_tags=[],
        )
        assert score < 0.75
