# -*- coding: utf-8 -*-
"""
工具函数
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import numpy as np


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    创建标准格式 logger

    Args:
        name:  logger 名称
        level: 日志级别

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger


def load_config(config_path: str) -> Dict[str, Any]:
    """加载 JSON 配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str, indent: int = 2) -> bool:
    """安全保存 JSON"""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception:
        return False


def format_duration(sec: float) -> str:
    """
    秒数转换为人类可读时长

    >>> format_duration(3661)
    '1h 1m 1s'
    """
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def compute_percentile(values: List[float], p: float) -> float:
    """计算百分位数"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * p / 100.0
    floor = int(idx)
    ceil = min(floor + 1, len(sorted_vals) - 1)
    weight = idx - floor
    return sorted_vals[floor] * (1 - weight) + sorted_vals[ceil] * weight


def moving_average(values: List[float], window: int) -> List[float]:
    """
    移动平均平滑

    Args:
        values: 输入序列
        window: 窗口大小

    Returns:
        平滑后的序列
    """
    if window < 1 or len(values) < window:
        return values[:]

    result = []
    for i in range(len(values) - window + 1):
        window_vals = values[i : i + window]
        result.append(sum(window_vals) / window)

    # 向前填充以保持长度一致
    pad_front = [result[0]] * (window - 1)
    return pad_front + result


def timestamp_to_datetime(ts_sec: float) -> datetime:
    """Unix 时间戳转 datetime"""
    from datetime import timezone
    return datetime.fromtimestamp(ts_sec, tz=timezone.utc)


def validate_subject_id(subject_id: str) -> bool:
    """验证受试者 ID 格式（字母+数字，长度 4-32）"""
    import re
    return bool(re.match(r"^[A-Za-z0-9]{4,32}$", subject_id))


def merge_stage_sequences(stages: List[Any]) -> List[Any]:
    """
    合并相邻的相同阶段标签

    Args:
        stages: SleepStage 列表

    Returns:
        合并后的阶段列表
    """
    if not stages:
        return []

    merged = [stages[0]]

    for stage in stages[1:]:
        last = merged[-1]
        if stage.label == last.label:
            # 合并到前一个
            last.end_sec = stage.end_sec
        else:
            merged.append(stage)

    return merged
