# -*- coding: utf-8 -*-
"""
Memory Server — AI Agent 记忆接口
==================================
提供 REST-style 接口，AI Agent 可通过 HTTP 调用。

启动：
  python -m agent_memory.server

接口：
  POST /offload        — 对话中途 offload 上下文
  GET  /load?q=        — 召回相关上下文
  POST /task/start     — 开始任务
  POST /task/complete  — 完成任务
  GET  /task/active    — 查询活跃任务
  GET  /knowledge?project= — 查询项目知识卡
  POST /dream/run      — 手动触发梦境整合（测试用）
  GET  /health         — 健康检查
"""

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify

from .offloader import MemoryOffloader
from .dream import DreamConsolidator
from .knowledge import KnowledgeCardStore
from .episodic import EpisodicStore


app = Flask(__name__)


# ── 全局 offloader 实例管理 ──────────────────────────────

_active_loaders: dict[str, MemoryOffloader] = {}


def get_or_create_loader(session_id: str, project: str = "") -> MemoryOffloader:
    if session_id not in _active_loaders:
        _active_loaders[session_id] = MemoryOffloader(
            session_id=session_id,
            project=project,
        )
    return _active_loaders[session_id]


# ── 接口 ────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/offload", methods=["POST"])
def offload():
    """POST /offload  {session_id, project, role, text, summary}"""
    body = request.json or {}
    session_id = body.get("session_id", "default")
    project = body.get("project", "")
    role = body.get("role", "mixed")
    text = body.get("text", "")
    summary = body.get("summary", "")
    force = body.get("force", False)

    loader = get_or_create_loader(session_id, project)
    loader.add_chunk(text, role=role)
    result = loader.offload_current(summary=summary, force=force)

    # 清理
    if session_id in _active_loaders and not _active_loaders[session_id]._current_turns:
        pass  # 保留，供后续 load 使用

    return jsonify(result)


@app.route("/load", methods=["GET"])
def load():
    """GET /load?session_id=xxx&q=关键词&project=&limit=20"""
    session_id = request.args.get("session_id", "default")
    query = request.args.get("q", "")
    project = request.args.get("project", "")
    limit = int(request.args.get("limit", 20))

    loader = get_or_create_loader(session_id, project)
    context = loader.load_context(query=query, project=project, limit=limit)

    return jsonify({"context": context, "query": query})


@app.route("/turn", methods=["POST"])
def add_turn():
    """POST /turn {session_id, project, role, text}"""
    body = request.json or {}
    session_id = body.get("session_id", "default")
    project = body.get("project", "")
    role = body.get("role", "user")
    text = body.get("text", "")

    loader = get_or_create_loader(session_id, project)
    loader.add_turn(role, text)

    return jsonify({"status": "ok", "turns_buffered": len(loader._current_turns)})


@app.route("/tool_call", methods=["POST"])
def tool_call():
    """POST /tool_call {session_id}"""
    body = request.json or {}
    session_id = body.get("session_id", "default")

    loader = _active_loaders.get(session_id)
    if not loader:
        return jsonify({"error": "session not found"}), 404

    loader.emit_tool_call()
    return jsonify({
        "tool_calls": loader._tool_call_count,
        "task_id": loader.task_id,
    })


@app.route("/task/start", methods=["POST"])
def task_start():
    """POST /task/start {session_id, project, task_id}"""
    body = request.json or {}
    session_id = body.get("session_id", "default")
    project = body.get("project", "")
    task_id = body.get("task_id")

    loader = MemoryOffloader(session_id=session_id, project=project, task_id=task_id)
    _active_loaders[session_id] = loader

    return jsonify({"task_id": loader.task_id, "project": project})


@app.route("/task/complete", methods=["POST"])
def task_complete():
    """POST /task/complete {session_id, summary}"""
    body = request.json or {}
    session_id = body.get("session_id", "default")
    summary = body.get("summary", "")

    loader = _active_loaders.get(session_id)
    if not loader:
        return jsonify({"error": "session not found"}), 404

    loader.offload_current(summary=summary, force=True)
    loader.complete_task(summary=summary)

    return jsonify({"task_id": loader.task_id, "status": "completed"})


@app.route("/task/active", methods=["GET"])
def task_active():
    """GET /task/active?project=xxx"""
    project = request.args.get("project", "")
    store = EpisodicStore()
    tasks = store.get_active_tasks(project=project if project else "")
    return jsonify({"tasks": tasks})


@app.route("/knowledge", methods=["GET"])
def knowledge_list():
    """GET /knowledge?project=xxx"""
    project = request.args.get("project", "")
    store = KnowledgeCardStore()
    if project:
        cards = store.get_by_project(project)
    else:
        cards = store.get_active_all()
    return jsonify({"cards": cards})


@app.route("/knowledge", methods=["POST"])
def knowledge_upsert():
    """POST /knowledge {project, title, content, trigger}"""
    body = request.json or {}
    project = body.get("project", "")
    title = body.get("title", "")
    content = body.get("content", "")
    trigger = body.get("trigger", "")
    source_task_id = body.get("task_id", "")

    if not project or not title:
        return jsonify({"error": "project and title required"}), 400

    store = KnowledgeCardStore()
    card_id = store.upsert(project, title, content, trigger, source_task_id)
    return jsonify({"card_id": card_id})


@app.route("/dream/run", methods=["POST"])
def dream_run():
    """POST /dream/run {date}"""
    body = request.json or {}
    date_str = body.get("date", date.today().isoformat())

    consolidator = DreamConsolidator(date_str=date_str)
    result = consolidator.run()
    return jsonify(result)


@app.route("/episodes", methods=["GET"])
def episodes():
    """GET /episodes?session_id=xxx&project=xxx&limit=50"""
    session_id = request.args.get("session_id")
    project = request.args.get("project")
    limit = int(request.args.get("limit", 50))

    store = EpisodicStore()
    if session_id:
        eps = store.get_session_episodes(session_id)
    else:
        eps = store.get_recent_episodes(project=project or None, limit=limit)
    return jsonify({"episodes": eps})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=38472, debug=False)
