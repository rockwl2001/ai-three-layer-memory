# -*- coding: utf-8 -*-
"""
Agent Memory System - 三层记忆系统 + 梦境整合
=============================================
架构：
  L0 工作记忆   → 内存中，随会话存活
  L1 情景记忆   → SQLite (episodes.db)，高精度上下文
  L2 语义记忆   → MEMORY.md / USER.md，长期沉淀

核心接口：
  MemoryOffloader        - 对话中途 offload/load 上下文
  DreamConsolidator      - 夜间 cron，梦境整合逻辑
  EpisodicStore          - L1 SQLite 情景记忆
  SemanticMemory         - L2 md 文件读写
"""

__version__ = "0.1.0"
