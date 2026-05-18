# -*- coding: utf-8 -*-
"""
数据模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum


class StageLabel(Enum):
    """AASM 睡眠阶段标签"""
    WAKE = "W"
    N1 = "N1"       # 入睡期
    N2 = "N2"       # 浅睡期
    N3 = "N3"       # 深睡期（慢波睡眠）
    REM = "REM"     # 快速眼动期
    UNKNOWN = "UNK"


@dataclass
class SleepStage:
    """
    单个睡眠阶段记录

    Attributes:
        label:       阶段标签
        start_sec:   开始时间（秒，相对记录起始）
        end_sec:     结束时间（秒）
        confidence:  分类置信度 [0, 1]
        features:    该阶段提取的特征向量
    """
    label: StageLabel
    start_sec: float
    end_sec: float
    confidence: float = 0.0
    features: Dict[str, float] = field(default_factory=dict)

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    @property
    def duration_min(self) -> float:
        return self.duration_sec / 60.0


@dataclass
class DreamContent:
    """
    梦境内容记录

    Attributes:
        stage:           对应睡眠阶段
        keywords:         提取的关键词列表
        emotions:         情感标签（如：紧张/平静/恐惧/愉悦）
        imagery_types:    意象类型（人物/场景/物体/活动等）
        lucidity:        清醒梦境指数 [0, 1]
        narrative:       简短叙事描述（可选）
    """
    stage: SleepStage
    keywords: List[str] = field(default_factory=list)
    emotions: List[str] = field(default_factory=list)
    imagery_types: List[str] = field(default_factory=list)
    lucidity: float = 0.0
    narrative: Optional[str] = None


@dataclass
class Subject:
    """
    受试者信息

    Attributes:
        subject_id:   受试者唯一标识
        age:          年龄
        gender:       性别（M/F/O）
        recordings:   该受试者的所有睡眠记录
    """
    subject_id: str
    age: int
    gender: str
    recordings: List["SleepRecording"] = field(default_factory=list)

    @property
    def total_sleep_hours(self) -> float:
        total = 0.0
        for rec in self.recordings:
            for stage in rec.stages:
                if stage.label not in (StageLabel.WAKE, StageLabel.UNKNOWN):
                    total += stage.duration_min
        return total / 60.0


@dataclass
class SleepRecording:
    """
    单次睡眠记录

    Attributes:
        recording_id:  记录唯一标识
        date:         记录日期
        subject:      受试者
        stages:       睡眠阶段列表
        dreams:       梦境内容列表
        notes:        备注（如睡前情绪、咖啡因摄入等）
    """
    recording_id: str
    date: date
    subject: Optional[Subject] = None
    stages: List[SleepStage] = field(default_factory=list)
    dreams: List[DreamContent] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)

    def stage_summary(self) -> Dict[StageLabel, float]:
        """返回各阶段总时长（分钟）"""
        summary: Dict[StageLabel, float] = {s: 0.0 for s in StageLabel}
        for s in self.stages:
            if s.label != StageLabel.UNKNOWN:
                summary[s.label] += s.duration_min
        return summary

    @property
    def sleep_efficiency(self) -> float:
        """
        睡眠效率 = (总睡眠时间 / 总记录时间) × 100%
        """
        total = sum(s.duration_min for s in self.stages)
        if not self.stages:
            return 0.0
        record_min = self.stages[-1].end_sec / 60.0
        return (total / record_min * 100) if record_min > 0 else 0.0
