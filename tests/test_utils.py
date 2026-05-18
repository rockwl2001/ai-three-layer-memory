# -*- coding: utf-8 -*-
"""
工具函数单元测试
"""

import pytest
from pathlib import Path
from three_layer_memory.utils import (
    format_duration,
    compute_percentile,
    moving_average,
    validate_subject_id,
    merge_stage_sequences,
    setup_logger,
)


class TestFormatDuration:
    """format_duration 测试"""

    def test_hour_minute_second(self):
        assert format_duration(3661) == "1h 1m 1s"

    def test_minute_only(self):
        assert format_duration(125) == "2m 5s"

    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_zero(self):
        assert format_duration(0) == "0s"


class TestComputePercentile:
    """compute_percentile 测试"""

    def test_median(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        assert abs(compute_percentile(vals, 50) - 5.5) < 0.1

    def test_empty_list(self):
        assert compute_percentile([], 50) == 0.0

    def test_single_value(self):
        assert compute_percentile([42.0], 90) == 42.0


class TestMovingAverage:
    """moving_average 测试"""

    def test_basic_smoothing(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = moving_average(data, window=3)
        assert len(result) == len(data)
        assert result[0] == result[1]  # pad_front
        assert abs(result[-1] - 4.0) < 0.01

    def test_window_larger_than_data(self):
        data = [1.0, 2.0]
        result = moving_average(data, window=5)
        assert result == data

    def test_window_one(self):
        data = [10.0, 20.0, 30.0]
        result = moving_average(data, window=1)
        assert result == data


class TestValidateSubjectId:
    """validate_subject_id 测试"""

    def test_valid_ids(self):
        assert validate_subject_id("S001") is True
        assert validate_subject_id("ABC12345") is True
        assert validate_subject_id("a" * 32) is True

    def test_too_short(self):
        assert validate_subject_id("S01") is False

    def test_special_characters(self):
        assert validate_subject_id("S-001") is False
        assert validate_subject_id("S_001") is False
        assert validate_subject_id("S 001") is False


class TestMergeStageSequences:
    """merge_stage_sequences 测试"""

    def test_merge_adjacent_same_label(self):
        from three_layer_memory.models import SleepStage, StageLabel

        stages = [
            SleepStage(label=StageLabel.REM, start_sec=0.0, end_sec=30.0),
            SleepStage(label=StageLabel.REM, start_sec=30.0, end_sec=60.0),
            SleepStage(label=StageLabel.N2, start_sec=60.0, end_sec=90.0),
        ]

        merged = merge_stage_sequences(stages)
        assert len(merged) == 2
        assert merged[0].label == StageLabel.REM
        assert merged[0].end_sec == 60.0  # 合并后
        assert merged[1].label == StageLabel.N2

    def test_no_merge_different_labels(self):
        from three_layer_memory.models import SleepStage, StageLabel

        stages = [
            SleepStage(label=StageLabel.WAKE, start_sec=0.0, end_sec=10.0),
            SleepStage(label=StageLabel.N1, start_sec=10.0, end_sec=20.0),
            SleepStage(label=StageLabel.N2, start_sec=20.0, end_sec=50.0),
        ]

        merged = merge_stage_sequences(stages)
        assert len(merged) == 3


class TestSetupLogger:
    """setup_logger 测试"""

    def test_logger_creation(self):
        logger = setup_logger("test_logger")
        assert logger.name == "test_logger"
        assert logger.level <= 20  # INFO level

    def test_duplicate_handlers(self):
        """多次调用 setup_logger 不应重复添加 handler"""
        logger = setup_logger("test_dup")
        h1_count = len(logger.handlers)
        setup_logger("test_dup")
        assert len(logger.handlers) == h1_count
