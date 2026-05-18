# -*- coding: utf-8 -*-
"""
模型单元测试
"""

import pytest
from datetime import date
from three_layer_memory.models import (
    SleepStage,
    DreamContent,
    Subject,
    SleepRecording,
    StageLabel,
)


class TestSleepStage:
    """SleepStage 数据类测试"""

    def test_duration_calculation(self):
        stage = SleepStage(
            label=StageLabel.REM,
            start_sec=0.0,
            end_sec=1800.0,  # 30 分钟
        )
        assert abs(stage.duration_sec - 1800.0) < 0.01
        assert abs(stage.duration_min - 30.0) < 0.01

    def test_unknown_label(self):
        stage = SleepStage(
            label=StageLabel.UNKNOWN,
            start_sec=100.0,
            end_sec=130.0,
        )
        assert stage.label == StageLabel.UNKNOWN
        assert stage.duration_sec == 30.0

    def test_confidence_range(self):
        stage = SleepStage(
            label=StageLabel.N2,
            start_sec=0.0,
            end_sec=30.0,
            confidence=0.85,
        )
        assert 0.0 <= stage.confidence <= 1.0
        assert stage.confidence == 0.85


class TestDreamContent:
    """DreamContent 测试"""

    def test_dream_with_keywords(self):
        stage = SleepStage(
            label=StageLabel.REM,
            start_sec=0.0,
            end_sec=1800.0,
        )
        dream = DreamContent(
            stage=stage,
            keywords=["飞翔", "学校", "童年"],
            emotions=["自由", "怀旧"],
            imagery_types=["人物", "场景"],
            lucidity=0.6,
            narrative="梦见自己在学校飞翔。",
        )

        assert len(dream.keywords) == 3
        assert "自由" in dream.emotions
        assert dream.lucidity == 0.6

    def test_lucidity_bounds(self):
        stage = SleepStage(label=StageLabel.REM, start_sec=0.0, end_sec=30.0)
        dream = DreamContent(stage=stage, lucidity=1.5)  # 超范围应被限制
        assert dream.lucidity <= 1.0


class TestSubject:
    """Subject 测试"""

    def test_total_sleep_hours(self):
        subject = Subject(
            subject_id="S001",
            age=30,
            gender="M",
            recordings=[],
        )

        rec = SleepRecording(
            recording_id="R001",
            date=date.today(),
            subject=subject,
        )

        # 添加 REM 阶段 2 小时
        rec.stages.append(
            SleepStage(label=StageLabel.REM, start_sec=0.0, end_sec=3600.0)
        )
        rec.stages.append(
            SleepStage(label=StageLabel.N2, start_sec=3600.0, end_sec=7200.0)
        )
        rec.stages.append(
            SleepStage(label=StageLabel.WAKE, start_sec=7200.0, end_sec=7500.0)
        )

        subject.recordings.append(rec)

        # 睡眠时间 = REM(1h) + N2(1h) = 2h
        assert abs(subject.total_sleep_hours - 2.0) < 0.1


class TestSleepRecording:
    """SleepRecording 测试"""

    def test_stage_summary(self):
        rec = SleepRecording(
            recording_id="R001",
            date=date.today(),
        )

        rec.stages = [
            SleepStage(label=StageLabel.WAKE, start_sec=0.0, end_sec=600.0),
            SleepStage(label=StageLabel.N1, start_sec=600.0, end_sec=900.0),
            SleepStage(label=StageLabel.N2, start_sec=900.0, end_sec=2700.0),
            SleepStage(label=StageLabel.REM, start_sec=2700.0, end_sec=4500.0),
        ]

        summary = rec.stage_summary()
        assert summary[StageLabel.N2] == 30.0  # 30 分钟
        assert summary[StageLabel.REM] == 30.0
        assert summary[StageLabel.WAKE] == 10.0

    def test_sleep_efficiency(self):
        rec = SleepRecording(
            recording_id="R001",
            date=date.today(),
        )
        rec.stages = [
            SleepStage(label=StageLabel.WAKE, start_sec=0.0, end_sec=1000.0),
            SleepStage(label=StageLabel.REM, start_sec=1000.0, end_sec=2800.0),
        ]

        # 睡眠效率 = (30分钟睡眠 / 46.7分钟总记录) ≈ 64%
        eff = rec.sleep_efficiency
        assert 60.0 < eff < 70.0

    def test_empty_recording_efficiency(self):
        rec = SleepRecording(recording_id="R002", date=date.today())
        assert rec.sleep_efficiency == 0.0
