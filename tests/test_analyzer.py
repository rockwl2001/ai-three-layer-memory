# -*- coding: utf-8 -*-
"""
分析器单元测试
"""

import pytest
import numpy as np
import json
import tempfile
from pathlib import Path

from three_layer_memory.analyzer import SleepAnalyzer
from three_layer_memory.models import StageLabel


class TestSleepAnalyzer:
    """SleepAnalyzer 主类测试"""

    @pytest.fixture
    def analyzer(self):
        return SleepAnalyzer(sample_rate=256)

    @pytest.fixture
    def eeg_csv_path(self, tmp_path):
        """生成测试用 CSV 文件"""
        csv_file = tmp_path / "test_eeg.csv"
        n = 256 * 600  # 10 分钟数据

        rows = ["time,eeg"]
        for i in range(n):
            t = i / 256.0
            # 模拟 alpha 波（10Hz）信号
            eeg = 10.0 * np.sin(2 * np.pi * 10 * t) + np.random.normal(0, 2)
            rows.append(f"{t:.4f},{eeg:.4f}")

        csv_file.write_text("\n".join(rows), encoding="utf-8")
        return str(csv_file)

    def test_load_eeg_csv(self, analyzer, eeg_csv_path):
        result = analyzer.load_eeg(eeg_csv_path)
        assert result is True
        assert analyzer._eeg_data is not None
        assert "eeg" in analyzer._eeg_data
        assert len(analyzer._eeg_data["eeg"]) > 0

    def test_load_eeg_json(self, analyzer, tmp_path):
        """测试 JSON 格式加载"""
        json_file = tmp_path / "test_eeg.json"
        n = 256 * 300
        time_arr = [round(i / 256.0, 4) for i in range(n)]
        eeg_arr = [round(5.0 * np.sin(2 * np.pi * 8 * time_arr[i]), 4) for i in range(n)]

        json_file.write_text(
            json.dumps({"time": time_arr, "eeg": eeg_arr}),
            encoding="utf-8",
        )

        result = analyzer.load_eeg(str(json_file))
        assert result is True

    def test_load_unsupported_format(self, analyzer, tmp_path):
        """不支持格式应返回 False"""
        bad_file = tmp_path / "test.xxx"
        bad_file.write_text("dummy", encoding="utf-8")
        assert analyzer.load_eeg(str(bad_file)) is False

    def test_auto_stage_without_data(self, analyzer):
        """未加载数据时 auto_stage 应返回空列表"""
        result = analyzer.auto_stage()
        assert result == []

    def test_auto_stage_produces_stages(self, analyzer, eeg_csv_path):
        """自动标注应产生非空结果"""
        analyzer.load_eeg(eeg_csv_path)
        stages = analyzer.auto_stage(epoch_sec=30.0)

        assert len(stages) > 0
        assert all(hasattr(s, "label") for s in stages)
        assert all(s.start_sec < s.end_sec for s in stages)
        assert all(isinstance(s.label, StageLabel) for s in stages)

    def test_stage_confidence_range(self, analyzer, eeg_csv_path):
        """置信度应在 [0, 1] 范围内"""
        analyzer.load_eeg(eeg_csv_path)
        stages = analyzer.auto_stage()
        for s in stages:
            assert 0.0 <= s.confidence <= 1.0

    def test_export_stages_json(self, analyzer, eeg_csv_path, tmp_path):
        """JSON 导出功能"""
        analyzer.load_eeg(eeg_csv_path)
        stages = analyzer.auto_stage()
        output_path = str(tmp_path / "stages_export.json")

        result = analyzer.export_stages_json(stages, output_path)
        assert result is True
        assert Path(output_path).exists()

        # 验证导出内容
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == len(stages)
        assert "label" in data[0]
        assert "start_sec" in data[0]

    def test_analyze_dreams_rem_only(self, analyzer, eeg_csv_path):
        """梦境分析默认仅处理 REM 期"""
        analyzer.load_eeg(eeg_csv_path)
        stages = analyzer.auto_stage()
        dreams = analyzer.analyze_dreams(stages, rem_only=True)

        # 所有梦境应来自 REM 期
        for d in dreams:
            assert d.stage.label == StageLabel.REM

    def test_report_summary(self, analyzer, eeg_csv_path):
        """报告摘要功能"""
        analyzer.load_eeg(eeg_csv_path)
        stages = analyzer.auto_stage()
        report = analyzer.generate_report(stages)

        summary = report.summary()
        assert "total_epochs" in summary
        assert "total_min" in summary
        assert summary["total_epochs"] == len(stages)


class TestSleepAnalyzerHelpers:
    """内部辅助方法测试"""

    def test_extract_features_shapes(self):
        """特征提取应返回合理数值"""
        analyzer = SleepAnalyzer(sample_rate=256)
        processor = analyzer.processor

        # 生成 30 秒伪随机信号
        t = np.linspace(0, 30, 256 * 30)
        signal = np.sin(2 * np.pi * 10 * t) + 0.5 * np.sin(2 * np.pi * 3 * t)

        features = analyzer._extract_epoch_features(signal)

        assert isinstance(features, dict)
        assert "alpha_power" in features
        assert "delta_power" in features
        assert features["alpha_power"] >= 0.0

    def test_classify_stage_rules(self):
        """阶段分类逻辑边界测试"""
        analyzer = SleepAnalyzer()

        # 高 alpha → WAKE
        wake_features = {"alpha_power": 0.5, "delta_power": 0.1, "theta_power": 0.1, "sigma_power": 0.01, "hjorth_mobility": 0.2, "hjorth_complexity": 1.0}
        assert analyzer._classify_stage(wake_features) == StageLabel.WAKE

        # 高 delta → N3
        n3_features = {"alpha_power": 0.05, "delta_power": 0.5, "theta_power": 0.1, "sigma_power": 0.01, "hjorth_mobility": 0.1, "hjorth_complexity": 0.8}
        assert analyzer._classify_stage(n3_features) == StageLabel.N3

    def test_emotion_inference(self):
        """情感推断"""
        analyzer = SleepAnalyzer()
        from three_layer_memory.models import SleepStage

        stage = SleepStage(label=StageLabel.REM, start_sec=0.0, end_sec=30.0)
        emotions = analyzer._infer_emotions(stage)
        assert isinstance(emotions, list)
        assert len(emotions) > 0

    def test_keyword_inference(self):
        """关键词推断"""
        analyzer = SleepAnalyzer()
        from three_layer_memory.models import SleepStage

        stage = SleepStage(label=StageLabel.N2, start_sec=0.0, end_sec=30.0)
        keywords = analyzer._infer_keywords(stage)
        assert "浅睡" in keywords or "纺锤波" in keywords

    def test_lucidity_estimation(self):
        """清醒指数估算"""
        analyzer = SleepAnalyzer()
        from three_layer_memory.models import SleepStage

        rem_stage = SleepStage(label=StageLabel.REM, start_sec=0.0, end_sec=30.0, confidence=0.8)
        rem_lucidity = analyzer._estimate_lucidity(rem_stage)
        assert 0.0 <= rem_lucidity <= 1.0
        assert rem_lucidity > 0.0

        wake_stage = SleepStage(label=StageLabel.WAKE, start_sec=0.0, end_sec=30.0)
        wake_lucidity = analyzer._estimate_lucidity(wake_stage)
        assert wake_lucidity == 0.0
