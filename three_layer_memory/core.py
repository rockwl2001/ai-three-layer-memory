# -*- coding: utf-8 -*-
"""
核心信号处理模块
"""

import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class SignalSegment:
    """信号片段"""
    data: np.ndarray
    start_sec: float
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.data) / self.sample_rate

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration


class SignalProcessor:
    """
    睡眠生理信号预处理器

    支持 EEG（脑电）、EMG（肌电）、EOG（眼电）三种信号的基础处理。
    """

    SUPPORTED_TYPES = ("eeg", "emg", "eog")

    # 各信号典型频率范围（Hz）
    BAND_RANGES = {
        "delta": (0.5, 4),
        "theta": (4, 8),
        "alpha": (8, 13),
        "sigma": (12, 16),   # 睡眠纺锤波
        "beta": (13, 30),
        "gamma": (30, 50),
    }

    def __init__(self, sample_rate: int = 256):
        self.sample_rate = sample_rate

    def bandpass_filter(
        self,
        data: np.ndarray,
        low_freq: float,
        high_freq: float,
        order: int = 4,
    ) -> np.ndarray:
        """
        带通滤波（巴特沃斯 IIR）

        Args:
            data:      输入信号
            low_freq:  低频截止（Hz）
            high_freq: 高频截止（Hz）
            order:     滤波器阶数

        Returns:
            滤波后信号
        """
        from scipy.signal import butter, filtfilt

        nyq = self.sample_rate / 2.0
        low = low_freq / nyq
        high = high_freq / nyq
        b, a = butter(order, [low, high], btype="band")
        return filtfilt(b, a, data)

    def extract_band_power(
        self, data: np.ndarray, band: str, window_sec: float = 30.0
    ) -> float:
        """
        计算指定频段的相对功率

        Args:
            data:       输入信号
            band:       频段名称（delta/theta/alpha/sigma/beta/gamma）
            window_sec: 分析窗口（秒）

        Returns:
            相对功率值（该频段功率/总功率）
        """
        from scipy.signal import welch

        low, high = self.BAND_RANGES[band]

        # 带通提取目标频段
        filtered = self.bandpass_filter(data, low, high)

        # 计算目标频段功率
        freqs, psd = welch(filtered, fs=self.sample_rate, nperseg=int(window_sec * self.sample_rate))

        band_power = np.trapezoid(psd, freqs)

        # 计算总功率
        freqs_all, psd_all = welch(data, fs=self.sample_rate, nperseg=int(window_sec * self.sample_rate))
        total_power = np.trapezoid(psd_all, freqs_all)

        if total_power == 0:
            return 0.0
        return band_power / total_power

    def detect_spindles(self, data: np.ndarray, min_duration_sec: float = 0.5) -> List[Tuple[float, float]]:
        """
        检测睡眠纺锤波（N2 期的特征波形）

        Returns:
            纺锤波起止时间列表 [(start_sec, end_sec), ...]
        """
        from scipy.signal import find_peaks

        # sigma 频段带通
        filtered = self.bandpass_filter(
            data,
            *self.BAND_RANGES["sigma"],
        )

        # RMS 包络
        rms = np.sqrt(np.convolve(filtered ** 2, np.ones(int(0.1 * self.sample_rate)) / 0.1, mode="same"))

        # 峰值检测
        threshold = np.mean(rms) + 1.5 * np.std(rms)
        peaks, _ = find_peaks(rms, height=threshold, distance=int(0.3 * self.sample_rate))

        spindle_events = []
        min_samples = int(min_duration_sec * self.sample_rate)

        for peak in peaks:
            left = peak
            while left > 0 and rms[left] > threshold:
                left -= 1
            right = peak
            while right < len(rms) - 1 and rms[right] > threshold:
                right += 1
            if right - left >= min_samples:
                start_sec = left / self.sample_rate
                end_sec = right / self.sample_rate
                spindle_events.append((start_sec, end_sec))

        return spindle_events

    def compute_hjorth_params(self, data: np.ndarray) -> Tuple[float, float, float]:
        """
        计算 Hjorth 参数：Activity、Mobility、Complexity

        Returns:
            (activity, mobility, complexity)
        """
        # 一阶差分
        diff1 = np.diff(data)
        diff2 = np.diff(diff1)

        var_diff1 = np.var(diff1) if len(diff1) > 0 else 0.0
        var_diff2 = np.var(diff2) if len(diff2) > 0 else 0.0
        activity = np.var(data) if len(data) > 0 else 0.0

        mobility = np.sqrt(var_diff1 / activity) if activity > 0 else 0.0
        complexity = np.sqrt(var_diff2 / var_diff1) / mobility if mobility > 0 and var_diff1 > 0 else 0.0

        return activity, mobility, complexity


def load_edf_signal(filepath: str) -> Tuple[np.ndarray, int, float]:
    """
    读取 EDF 格式睡眠信号文件

    Returns:
        (data, sample_rate, duration_sec)
    """
    import struct

    with open(filepath, "rb") as f:
        # EDF 头解析
        header = f.read(256)
        # 简化解析（实际应完整实现 EDF 规范）
        sample_rate = 256  # 默认值

    data = np.array([])
    duration_sec = 0.0
    return data, sample_rate, duration_sec
