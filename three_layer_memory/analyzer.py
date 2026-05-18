# -*- coding: utf-8 -*-
"""
主分析器 - 整合信号处理、阶段标注与梦境分析
"""

import json
import logging
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import numpy as np

from .models import SleepStage, SleepRecording, StageLabel, DreamContent, Subject
from .core import SignalProcessor, SignalSegment

log = logging.getLogger(__name__)


class SleepAnalyzer:
    """
    睡眠分析主类

    使用示例::

        analyzer = SleepAnalyzer()
        analyzer.load_eeg("sleep_data.csv")
        stages = analyzer.auto_stage()
        report = analyzer.generate_report(stages)
        report.save("output/report.pdf")
    """

    STAGE_THRESHOLDS = {
        StageLabel.WAKE:  {"alpha_ratio": 0.3, "motion": 0.5},
        StageLabel.N1:   {"alpha_ratio": 0.1, "theta_ratio": 0.3},
        StageLabel.N2:   {"sigma_present": True, "k_complex": False},
        StageLabel.N3:   {"delta_ratio": 0.4, "slow_wave": 0.6},
        StageLabel.REM:  {"rem_signature": True, "atonia": True},
    }

    def __init__(
        self,
        sample_rate: int = 256,
        use_gpu: bool = False,
        model_path: Optional[str] = None,
    ):
        self.sample_rate = sample_rate
        self.use_gpu = use_gpu
        self.model_path = model_path
        self.processor = SignalProcessor(sample_rate=sample_rate)
        self._eeg_data: Optional[Dict[str, np.ndarray]] = None
        self._recording: Optional[SleepRecording] = None

    def load_eeg(self, filepath: str) -> bool:
        """
        加载 EEG 数据文件（支持 CSV/JSON）

        Returns:
            加载是否成功
        """
        path = Path(filepath)
        suffix = path.suffix.lower()

        try:
            if suffix == ".csv":
                import numpy as np
                import csv

                with open(filepath, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)

                if not rows:
                    return False

                time_col = [float(r["time"]) for r in rows if "time" in r]
                eeg_col = [float(r["eeg"]) for r in rows if "eeg" in r]

                self._eeg_data = {
                    "time": np.array(time_col),
                    "eeg": np.array(eeg_col),
                }
                log.info(f"已加载 CSV，共 {len(eeg_col)} 个采样点")
                return True

            elif suffix == ".json":
                import numpy as np
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                self._eeg_data = {
                    "time": np.array(raw.get("time", [])),
                    "eeg": np.array(raw.get("eeg", [])),
                }
                log.info("已加载 JSON EEG 数据")
                return True

            else:
                log.error(f"不支持的文件格式: {suffix}")
                return False

        except Exception as e:
            log.error(f"加载 EEG 文件失败: {e}")
            return False

    def auto_stage(self, epoch_sec: float = 30.0) -> List[SleepStage]:
        """
        基于规则自动标注睡眠阶段（AASM 标准）

        Args:
            epoch_sec: 分段窗口长度（秒），默认 30 秒

        Returns:
            睡眠阶段列表
        """
        if self._eeg_data is None:
            log.error("请先调用 load_eeg 加载数据")
            return []

        eeg = self._eeg_data["eeg"]
        time_arr = self._eeg_data["time"]
        total_sec = time_arr[-1] if len(time_arr) > 0 else 0.0

        n_epochs = int(total_sec / epoch_sec)
        stages: List[SleepStage] = []

        for i in range(n_epochs):
            start_sec = i * epoch_sec
            end_sec = start_sec + epoch_sec

            # 截取该 epoch 的信号
            mask = (time_arr >= start_sec) & (time_arr < end_sec)
            epoch_data = eeg[mask]

            if len(epoch_data) == 0:
                continue

            # 提取特征
            features = self._extract_epoch_features(epoch_data)

            # 基于特征推断阶段
            label = self._classify_stage(features)
            confidence = min(features.get("confidence", 0.5) + 0.3, 0.95)

            stages.append(
                SleepStage(
                    label=label,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    confidence=confidence,
                    features=features,
                )
            )

        log.info(f"阶段标注完成，共 {len(stages)} 个 epoch")
        return stages

    def _extract_epoch_features(self, epoch_data: np.ndarray) -> Dict[str, float]:
        """为单个 epoch 提取特征向量"""
        import numpy as np

        features = {}

        # 相对频段功率（各频段占总功率的比例）
        for band in ["delta", "theta", "alpha", "sigma", "beta"]:
            features[f"{band}_power"] = self.processor.extract_band_power(
                epoch_data, band, window_sec=len(epoch_data) / self.sample_rate
            )

        # Hjorth 参数
        act, mob, com = self.processor.compute_hjorth_params(epoch_data)
        features["hjorth_activity"] = act
        features["hjorth_mobility"] = mob
        features["hjorth_complexity"] = com

        # 幅值统计
        features["signal_mean"] = float(np.mean(epoch_data))
        features["signal_std"] = float(np.std(epoch_data))
        features["signal_range"] = float(np.ptp(epoch_data))

        # 经验置信度（特征完整性指标）
        features["confidence"] = 0.5

        return features

    def _classify_stage(self, features: Dict[str, float]) -> StageLabel:
        """基于特征向量判断睡眠阶段"""
        alpha = features.get("alpha_power", 0.0)
        delta = features.get("delta_power", 0.0)
        theta = features.get("theta_power", 0.0)
        sigma = features.get("sigma_power", 0.0)
        mobility = features.get("hjorth_mobility", 0.0)
        complexity = features.get("hjorth_complexity", 0.0)

        # 唤醒期：alpha 活动明显
        if alpha > 0.25:
            return StageLabel.WAKE

        # REM 期：alpha 中等，theta 活跃，肌电降低
        if theta > 0.20 and sigma > 0.05:
            if mobility > 0.5 and complexity > 1.2:
                return StageLabel.REM

        # 深睡眠期：delta 主导
        if delta > 0.35:
            return StageLabel.N3

        # 浅睡 N2：有纺锤波或 K 复合波特征
        if sigma > 0.04 or (mobility > 0.3 and complexity > 1.0):
            return StageLabel.N2

        # 入睡 N1：alpha 降低，theta 开始出现
        if theta > 0.15 or alpha < 0.15:
            return StageLabel.N1

        return StageLabel.UNKNOWN

    def analyze_dreams(
        self, stages: List[SleepStage], rem_only: bool = True
    ) -> List[DreamContent]:
        """
        梦境内容分析（REM 期梦境特征提取）

        Args:
            stages:   睡眠阶段列表
            rem_only: 是否仅分析 REM 期

        Returns:
            梦境内容列表
        """
        dreams: List[DreamContent] = []

        for stage in stages:
            if rem_only and stage.label != StageLabel.REM:
                continue

            # 从阶段特征推断梦境属性
            emotions = self._infer_emotions(stage)
            keywords = self._infer_keywords(stage)
            imagery = self._infer_imagery(stage)
            lucidity = self._estimate_lucidity(stage)

            dreams.append(
                DreamContent(
                    stage=stage,
                    keywords=keywords,
                    emotions=emotions,
                    imagery_types=imagery,
                    lucidity=lucidity,
                )
            )

        log.info(f"梦境分析完成，共 {len(dreams)} 个梦境片段")
        return dreams

    def _infer_emotions(self, stage: SleepStage) -> List[str]:
        """从信号特征推断梦境情感"""
        emotion_map = {
            StageLabel.REM: ["复杂", "生动"],
            StageLabel.N1: ["模糊", "片段"],
            StageLabel.N2: ["平静"],
            StageLabel.N3: ["深沉"],
            StageLabel.WAKE: ["清醒"],
        }
        return emotion_map.get(stage.label, ["未知"])

    def _infer_keywords(self, stage: SleepStage) -> List[str]:
        """从阶段特征推断梦境关键词"""
        keywords_map = {
            StageLabel.REM: ["梦境", "REM", "快速眼动"],
            StageLabel.N2: ["浅睡", "纺锤波"],
            StageLabel.N3: ["深度睡眠", "恢复性睡眠"],
        }
        return keywords_map.get(stage.label, [])

    def _infer_imagery(self, stage: SleepStage) -> List[str]:
        """推断梦境意象类型"""
        return ["人物", "场景"] if stage.label == StageLabel.REM else []

    def _estimate_lucidity(self, stage: SleepStage) -> float:
        """估算清醒梦境指数"""
        if stage.label == StageLabel.WAKE:
            return 0.0
        if stage.label == StageLabel.REM:
            return 0.4 + 0.2 * stage.confidence
        return 0.0

    def generate_report(
        self, stages: List[SleepStage], output_path: Optional[str] = None
    ) -> "Report":
        """生成睡眠分析报告"""
        return Report(stages, self._recording)

    def export_stages_json(self, stages: List[SleepStage], path: str) -> bool:
        """导出阶段数据为 JSON"""
        try:
            data = [
                {
                    "label": s.label.value,
                    "start_sec": s.start_sec,
                    "end_sec": s.end_sec,
                    "confidence": s.confidence,
                    "duration_min": s.duration_min,
                    "features": s.features,
                }
                for s in stages
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            log.error(f"导出 JSON 失败: {e}")
            return False


class Report:
    """睡眠报告"""

    def __init__(self, stages: List[SleepStage], recording: Optional[SleepRecording]):
        self.stages = stages
        self.recording = recording

    def summary(self) -> Dict[str, Any]:
        """报告摘要"""
        summary_dict: Dict[StageLabel, int] = {s: 0 for s in StageLabel}
        for s in self.stages:
            summary_dict[s.label] += 1

        total_min = sum(s.duration_min for s in self.stages)
        rem_min = sum(s.duration_min for s in self.stages if s.label == StageLabel.REM)
        n3_min = sum(s.duration_min for s in self.stages if s.label == StageLabel.N3)

        return {
            "total_epochs": len(self.stages),
            "total_min": round(total_min, 1),
            "rem_min": round(rem_min, 1),
            "n3_min": round(n3_min, 1),
            "stage_counts": {s.value: c for s, c in summary_dict.items()},
        }

    def save(self, path: str) -> bool:
        """保存报告（目前仅支持文本格式）"""
        try:
            lines = ["=" * 50, "Sleep & Dream Analysis Report", "=" * 50]
            summary = self.summary()
            for k, v in summary.items():
                lines.append(f"  {k}: {v}")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except Exception:
            return False
