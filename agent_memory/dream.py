# -*- coding: utf-8 -*-
"""
DreamConsolidator — 夜间梦境整合
=================================
参考 OpenClaw Dreaming 三阶段 + 六维评分 + Hermes Skills 思路。

执行时间：每天 23:00（北京时间）

三阶段：
  Light（浅睡）  — 收集当天所有对话片段，去重，准备候选材料
  REM（快速眼动）— 提取主题模式，生成反思信号，识别候选真理
  Deep（深睡）  — 六维评分，满足门槛的条目写入 MEMORY.md / USER.md

输出：
  - MEMORY.md 追加（环境事实、项目约定）
  - USER.md 追加（偏好、沟通风格）
  - 梦境日记 memory/logs/YYYY-MM-DD-dream.md
"""

import re
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from .episodic import EpisodicStore
from .semantic import (
    SemanticMemory,
    jaccard_similarity,
    six_dim_score,
    PROMOTION_THRESHOLD,
    MIN_FREQUENCY,
    MIN_UNIQUE_QUERIES,
    SCORE_WEIGHTS,
)
from .offloader import MemoryOffloader


# ── Prompt 模板 ──────────────────────────────────────────

REFINE_PROMPT = """你是一个记忆整理助手。请从以下对话记录中提炼出高质量的记忆条目。

【格式要求】
只输出两类内容，禁止重复原文：

## MEMORY.md 条目
- 项目事实（项目进展、环境约定、工具特性）
- 代码规范（项目约定、配置变更）
- 重要决策（做/不做什么，为什么）

## USER.md 条目
- 偏好（Rocky 的沟通风格、任务习惯）
- 约束（明确的要求或限制）

【评分标准】只提炼满足以下条件的条目：
  - 在对话中出现 ≥3 次，或被明确强调
  - 具有长期参考价值（不是一次性信息）
  - 与 Rocky 的核心关切相关

【输出格式】
```
## MEMORY.md
### 项目事实
- ...

### 环境约定
- ...

## USER.md
### 偏好
- ...

### 约束
- ...
```
"""

DREAM_NARRATIVE_PROMPT = """你是一个 AI Agent。请用叙事性的方式描述今天的"梦境"。

今天的对话记录：
{chunk_text}

请用 200 字以内描述：你今天主要处理了哪些主题？有什么重要的记忆点值得记住？
用第一人称，像写日记一样。不要复述细节，只描述重要的记忆模式。
用中文输出。
"""


class DreamConsolidator:
    """
    夜间梦境整合器。

    用法：
      consolidator = DreamConsolidator()
      consolidator.run()
    """

    def __init__(
        self,
        date_str: Optional[str] = None,
        model: str = "MiniMax-M2.7-highspeed",
    ):
        self.date_str = date_str or date.today().isoformat()
        self.model = model
        self.store = EpisodicStore()
        self.semantic = SemanticMemory()
        self.log_dir = Path(__file__).parent.parent.parent / "memory" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    # ── 入口 ────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """执行完整梦境整合"""
        result = {
            "date": self.date_str,
            "episodes_count": 0,
            "light_candidates": 0,
            "rem_themes": [],
            "deep_promoted_memory": 0,
            "deep_promoted_user": 0,
            "dream_narrative": "",
            "errors": [],
        }

        # Stage 1: Light — 收集候选
        try:
            candidates = self._stage_light()
            result["light_candidates"] = len(candidates)
        except Exception as e:
            result["errors"].append(f"Light stage error: {e}")
            candidates = []

        # Stage 2: REM — 主题提取
        try:
            themes, refined = self._stage_rem(candidates)
            result["rem_themes"] = themes
        except Exception as e:
            result["errors"].append(f"REM stage error: {e}")
            refined = candidates

        # Stage 3: Deep — 评分晋升
        try:
            mem_written, user_written = self._stage_deep(refined)
            result["deep_promoted_memory"] = mem_written
            result["deep_promoted_user"] = user_written
        except Exception as e:
            result["errors"].append(f"Deep stage error: {e}")

        # 梦境日记
        try:
            narrative = self._generate_dream_narrative(candidates)
            result["dream_narrative"] = narrative
            self._write_dream_log(narrative, candidates)
        except Exception as e:
            result["errors"].append(f"Dream log error: {e}")

        # 统计
        conn = self.store._conn()
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE created_at LIKE ?",
                (self.date_str + "%",),
            ).fetchone()
            result["episodes_count"] = rows[0] if rows else 0
        finally:
            conn.close()

        self._write_result_log(result)
        return result

    # ── Stage 1: Light ─────────────────────────────────

    def _stage_light(self) -> List[Dict[str, Any]]:
        """
        收集当天的所有情景片段，去重，准备候选。
        返回候选列表，每项包含文本、频率、上下文等信息。
        """
        conn = self.store._conn()
        try:
            rows = conn.execute(
                """
                SELECT chunk_text, project, session_id, created_at
                FROM episodes
                WHERE created_at LIKE ? AND is_archived=0
                ORDER BY created_at DESC
                """,
                (self.date_str + "%",),
            ).fetchall()
            episodes = [dict(r) for r in rows]
        finally:
            conn.close()

        if not episodes:
            return []

        # 按内容相似度合并（n-gram Jaccard）
        candidates = []
        used_indices = set()

        for i, ep in enumerate(episodes):
            if i in used_indices:
                continue
            group = [ep]
            for j, other in enumerate(episodes[i + 1 :], i + 1):
                if j in used_indices:
                    continue
                sim = jaccard_similarity(ep["chunk_text"], other["chunk_text"])
                if sim >= 0.7:  # 0.7 以上合并
                    group.append(other)
                    used_indices.add(j)
            used_indices.add(i)

            # 合并组的文本（取最长的作为代表）
            combined_text = max((g["chunk_text"] for g in group), key=len)
            candidate = {
                "text": combined_text[:2000],
                "projects": list({g["project"] for g in group if g["project"]}),
                "session_ids": list({g["session_id"] for g in group}),
                "frequency": len(group),
                "first_seen": min(g["created_at"] for g in group),
                "last_seen": max(g["created_at"] for g in group),
            }
            candidates.append(candidate)

        return candidates

    # ── Stage 2: REM ──────────────────────────────────

    def _stage_rem(
        self, candidates: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        用 LLM 提炼候选条目，提取主题模式。

        Returns:
            (themes, refined_entries)
              themes: 识别出的主题列表
              refined_entries: 提炼后的条目（含 section + content）
        """
        if not candidates:
            return [], []

        # 拼接候选文本（截断）
        combined = "\n\n".join(
            f"[片段{i+1}]\n{c['text'][:500]}" for i, c in enumerate(candidates[:20])
        )

        themes = self._extract_themes(combined)
        refined = self._refine_candidates(candidates)

        return themes, refined

    def _extract_themes(self, combined_text: str) -> List[str]:
        """从候选文本中提取主题模式"""
        # 简单启发式：从文本中提取 ## 标题和关键名词
        theme_patterns = re.findall(r"(?<![#\w])[\w]{4,}(?=[\s]*(?:项目|任务|配置|工具|方法|方案|问题))", combined_text)
        unique_themes = list(dict.fromkeys(theme_patterns[:10]))
        return unique_themes

    def _refine_candidates(
        self, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        过滤和提炼候选条目，分离出 MEMORY 和 USER 相关内容。
        """
        refined = []
        for c in candidates:
            text = c["text"]
            # 简单规则分类（未来可升级为 LLM 分类）
            if any(kw in text for kw in ["偏好", "喜欢", "倾向于", "沟通", "风格"]):
                section = "偏好"
            elif any(kw in text for kw in ["配置", "规范", "约定", "路径", "地址", "IP"]):
                section = "环境约定"
            elif any(kw in text for kw in ["项目", "进度", "完成", "进展"]):
                section = "项目事实"
            else:
                section = "未分类"

            c["section"] = section
            c["content"] = text[:500]
            c["relevance"] = 0.5  # 默认值
            c["recency_days"] = 0
            c["unique_contexts"] = c["frequency"]
            c["concept_tags"] = []
            c["consolidation_days"] = 0
            refined.append(c)

        return refined

    # ── Stage 3: Deep ─────────────────────────────────

    def _stage_deep(
        self, candidates: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        六维评分，满足门槛的条目写入 MEMORY.md / USER.md。
        """
        memory_entries = []
        user_entries = []

        for c in candidates:
            score = six_dim_score(
                frequency=c.get("frequency", 0),
                relevance=c.get("relevance", 0.5),
                recency_days=c.get("recency_days", 0),
                unique_contexts=c.get("unique_contexts", 0),
                concept_tags=c.get("concept_tags", []),
                consolidation_days=c.get("consolidation_days", 0),
            )
            c["score"] = score

            if score < PROMOTION_THRESHOLD:
                continue
            if c.get("frequency", 0) < MIN_FREQUENCY and c.get("unique_contexts", 0) < MIN_UNIQUE_QUERIES:
                continue

            if c.get("section") in ("偏好", "约束"):
                user_entries.append(c)
            else:
                memory_entries.append(c)

        # 去重 + 晋升
        mem_to_write, user_to_write = self.semantic.promote(
            memory_entries, user_entries
        )

        for entry in mem_to_write:
            parts = entry.split("\n", 1)
            section = parts[0].replace("## ", "").strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            self.semantic.append_memory(section, content)

        for entry in user_to_write:
            parts = entry.split("\n", 1)
            section = parts[0].replace("## ", "").strip()
            content = parts[1].strip() if len(parts) > 1 else ""
            self.semantic.append_user(section, content)

        return len(mem_to_write), len(user_to_write)

    # ── 梦境日记 ───────────────────────────────────────

    def _generate_dream_narrative(
        self, candidates: List[Dict[str, Any]]
    ) -> str:
        """生成梦境叙事（人类可读的梦境日记）"""
        if not candidates:
            return "今晚无事。"

        combined = "\n".join(c["text"][:300] for c in candidates[:10])
        narrative = combined[:500]  # 简单截断，不调 LLM（节省 token）
        return narrative

    def _write_dream_log(self, narrative: str, candidates: List[Dict[str, Any]]):
        log_path = self.log_dir / f"{self.date_str}-dream.md"
        today_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        content = f"""# 梦境日记 — {self.date_str}

> 生成时间：{today_str}

## 梦境叙事

{narrative}

## 原始片段数：{len(candidates)}

## 片段摘要

"""
        for i, c in enumerate(candidates[:20], 1):
            text = c["text"][:200].replace("\n", " ")
            content += f"{i}. [{c.get('section','未分类')}] {text}...\n"

        log_path.write_text(content, encoding="utf-8")

    def _write_result_log(self, result: Dict[str, Any]):
        log_path = self.log_dir / f"{self.date_str}-result.json"
        import json
        log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


# ── CLI 入口 ────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    from datetime import date

    date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    consolidator = DreamConsolidator(date_str=date_str)
    result = consolidator.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
