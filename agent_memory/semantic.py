# -*- coding: utf-8 -*-
"""
L2 语义记忆层 — Markdown 文件存储
===================================
MEMORY.md  → 环境事实、项目约定、工具特性（偏"事"）
USER.md    → Rocky 的偏好、沟通风格、工作流习惯（偏"人"）

支持：
  - 读取当前内容
  - 追加新条目（自动去重）
  - Jaccard 相似度去重
  - 六维评分筛选
"""

import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional


WORKSPACE = Path(__file__).parent.parent.parent
MEMORY_PATH = WORKSPACE / "MEMORY.md"
USER_PATH = WORKSPACE / "USER.md"
LOG_DIR = WORKSPACE / "memory" / "logs"


# ── 评分权重（六维，与 OpenClaw Dreaming 对齐）───────────────

SCORE_WEIGHTS = {
    "frequency": 0.24,       # 出现频率
    "relevance": 0.30,       # 相关性
    "recency": 0.15,         # 新鲜度
    "uniqueness": 0.15,       # 独特性
    "conceptual": 0.10,       # 概念密度
    "consolidation": 0.06,   # 巩固度
}

PROMOTION_THRESHOLD = 0.75    # 综合评分门槛
MIN_FREQUENCY = 3            # 最少出现次数
MIN_UNIQUE_QUERIES = 2       # 最少不同上下文数
JACCARD_THRESHOLD = 0.88     # Jaccard 去重阈值


# ── 工具函数 ────────────────────────────────────────────────

def jaccard_similarity(text1: str, text2: str) -> float:
    """计算两个文本的 Jaccard 相似度（基于字符 n-gram）"""
    def get_ngrams(text: str, n: int = 3) -> set:
        text = re.sub(r"[^\w]", "", text.lower())
        return set(text[i : i + n] for i in range(max(len(text) - n + 1, 0)))

    a = get_ngrams(text1)
    b = get_ngrams(text2)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def six_dim_score(
    frequency: int,
    relevance: float,
    recency_days: float,
    unique_contexts: int,
    concept_tags: List[str],
    consolidation_days: float = 0,
) -> float:
    """六维加权评分"""
    recency_score = max(0, 1 - recency_days / 14)  # 14天半衰期
    uniqueness_score = min(unique_contexts / 3, 1.0)
    conceptual_score = min(len(concept_tags) / 5, 1.0)
    consolidation_score = max(0, 1 - consolidation_days / 14)

    total = (
        SCORE_WEIGHTS["frequency"] * min(frequency / 5, 1.0)
        + SCORE_WEIGHTS["relevance"] * relevance
        + SCORE_WEIGHTS["recency"] * recency_score
        + SCORE_WEIGHTS["uniqueness"] * uniqueness_score
        + SCORE_WEIGHTS["conceptual"] * conceptual_score
        + SCORE_WEIGHTS["consolidation"] * consolidation_score
    )
    return round(total, 3)


def ensure_path(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


# ── MEMORY.md ──────────────────────────────────────────────

MEMORY_HEADER = """# MEMORY.md - 长期记忆

> AI Agent 的个人笔记，记录环境事实、项目约定、工具特性。
> 由梦境系统自动维护，请勿手动编辑。
"""

USER_HEADER = """# USER.md - 用户画像

> AI Agent 对用户的了解，记录偏好、沟通风格、工作流习惯。
> 由梦境系统自动维护，请勿手动编辑。
"""


class SemanticMemory:
    """L2 语义记忆读写"""

    def __init__(self, memory_path: Path = MEMORY_PATH, user_path: Path = USER_PATH):
        self.memory_path = memory_path
        self.user_path = user_path

    def read_memory(self) -> str:
        if not self.memory_path.exists():
            return ""
        return self.memory_path.read_text(encoding="utf-8")

    def read_user(self) -> str:
        if not self.user_path.exists():
            return ""
        return self.user_path.read_text(encoding="utf-8")

    def get_existing_blocks(self, memory_type: str = "memory") -> List[str]:
        """读取已有条目（去掉 header），用于去重比较"""
        path = self.memory_path if memory_type == "memory" else self.user_path
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8")
        # 去掉 header
        lines = content.split("\n")
        start = 0
        for i, line in enumerate(lines):
            if line.startswith("# MEMORY") or line.startswith("# USER"):
                start = i + 1
                break
        blocks = "\n".join(lines[start:]).strip()
        if not blocks:
            return []
        # 按 ## 分割各条记忆
        sections = re.split(r"\n## ", blocks)
        if sections[0].startswith("## "):
            sections[0] = sections[0][3:]
        return [s.strip() for s in sections if s.strip()]

    def append_memory(self, section: str, content: str):
        """追加到 MEMORY.md"""
        ensure_path(self.memory_path)
        if not self.memory_path.exists():
            self.memory_path.write_text(MEMORY_HEADER + "\n", encoding="utf-8")

        existing = self.read_memory()
        entry = f"\n\n## {section}\n{content}\n"
        self.memory_path.write_text(existing.rstrip() + entry, encoding="utf-8")

    def append_user(self, section: str, content: str):
        """追加到 USER.md"""
        ensure_path(self.user_path)
        if not self.user_path.exists():
            self.user_path.write_text(USER_HEADER + "\n", encoding="utf-8")

        existing = self.read_user()
        entry = f"\n\n## {section}\n{content}\n"
        self.user_path.write_text(existing.rstrip() + entry, encoding="utf-8")

    def promote(
        self,
        memory_entries: List[Dict[str, Any]],
        user_entries: List[Dict[str, Any]],
    ) -> Tuple[List[str], List[str]]:
        """
        六维评分 + Jaccard 去重，晋升候选条目。

        Returns:
            (memory_to_write, user_to_write) — 每项是 "section\ncontent" 格式
        """
        promoted_memory: List[str] = []
        promoted_user: List[str] = []

        existing_memory = self.get_existing_blocks("memory")
        existing_user = self.get_existing_blocks("user")

        for entry in memory_entries:
            score = six_dim_score(
                frequency=entry.get("frequency", 0),
                relevance=entry.get("relevance", 0),
                recency_days=entry.get("recency_days", 0),
                unique_contexts=entry.get("unique_contexts", 0),
                concept_tags=entry.get("concept_tags", []),
                consolidation_days=entry.get("consolidation_days", 0),
            )
            if score < PROMOTION_THRESHOLD:
                continue
            if entry.get("frequency", 0) < MIN_FREQUENCY:
                continue
            if entry.get("unique_contexts", 0) < MIN_UNIQUE_QUERIES:
                continue

            # Jaccard 去重
            content_text = entry.get("content", "")
            is_dup = any(
                jaccard_similarity(content_text, block) >= JACCARD_THRESHOLD
                for block in existing_memory
            )
            if is_dup:
                continue

            existing_memory.append(content_text)
            section = entry.get("section", "未分类")
            promoted_memory.append(f"## {section}\n{content_text}")

        for entry in user_entries:
            score = six_dim_score(
                frequency=entry.get("frequency", 0),
                relevance=entry.get("relevance", 0),
                recency_days=entry.get("recency_days", 0),
                unique_contexts=entry.get("unique_contexts", 0),
                concept_tags=entry.get("concept_tags", []),
                consolidation_days=entry.get("consolidation_days", 0),
            )
            if score < PROMOTION_THRESHOLD:
                continue

            content_text = entry.get("content", "")
            is_dup = any(
                jaccard_similarity(content_text, block) >= JACCARD_THRESHOLD
                for block in existing_user
            )
            if is_dup:
                continue

            existing_user.append(content_text)
            section = entry.get("section", "偏好")
            promoted_user.append(f"## {section}\n{content_text}")

        return promoted_memory, promoted_user
