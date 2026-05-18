# Agent Memory System — AI Agent 三层记忆系统

> 让 AI Agent 拥有跨会话的持久记忆，支持对话中途 offload / load，以及夜间梦境自动整合。

## 架构

```
L0  工作记忆   → 内存，对话存活
L1  情景记忆   → SQLite (episodes.db)，高精度上下文
L2  语义记忆   → MEMORY.md（事实） + USER.md（偏好），长期沉淀
L2  项目知识卡 → SQLite (episodes.db project_knowledge 表)，可复用技能
```

## 核心模块

| 模块 | 用途 |
|------|------|
| `agent_memory.episodic` | L1 SQLite 情景记忆，读写对话片段、任务状态 |
| `agent_memory.semantic` | L2 Markdown 读写，六维评分 + Jaccard 去重 |
| `agent_memory.offloader` | 对话中途 offload/load 接口 |
| `agent_memory.dream` | 夜间梦境整合（Light→REM→Deep 三阶段） |
| `agent_memory.knowledge` | 项目知识卡存储（Hermes Skills 思路） |
| `agent_memory.server` | REST API 接口，供 AI Agent 调用 |

## 安装

```bash
pip install -e .
```

## 接口服务器

```bash
python -m agent_memory.server
```

启动后访问 `http://127.0.0.1:38472/`。

## 核心接口

### 对话中途 Offload

```python
from agent_memory.offloader import MemoryOffloader

loader = MemoryOffloader(session_id="session_001", project="video2text")

# 用户消息后
loader.add_turn("user", "我想继续昨天的转写任务")

# AI 回复后
loader.add_turn("assistant", "好的，找到你的任务 ID...")

# 工具调用后（≥5次自动创建知识卡）
loader.emit_tool_call()

# 任务切换或结束
loader.offload_current(summary="用户想继续 video2text 任务")
```

### 召回上下文

```python
context = loader.load_context(
    query="昨天那个转写任务进展如何",
    project="video2text",
)
# → 返回相关记忆片段拼接文本
```

### 夜间梦境整合（cron）

```bash
python -m agent_memory.dream
```

每天 23:00 自动运行：
1. Light：收集当天所有情景片段
2. REM：提取主题模式
3. Deep：六维评分，满足门槛的条目写入 MEMORY.md / USER.md

## 数据库

SQLite 文件：`agent_memory/episodes.db`（自动创建）

表：
- `episodes` — 情景片段
- `tasks` — 任务状态
- `offload_log` — offload 历史
- `daily_summaries` — 每日摘要
- `project_knowledge` — 项目知识卡

## 参考

- OpenClaw Dreaming：三阶段（Light/REM/Deep）+ 六维评分
- Hermes Agent：MEMORY.md/USER.md 双文件 + Skills 闭环
- 腾讯 TencentDB Agent Memory：Context Offloading + Mermaid 任务图
