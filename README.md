# AI Agent 三层记忆系统与梦境系统

> 探索睡眠阶段与梦境内容关联性的开源工具包

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 概述

本项目是一个基于 AI Agent 三层记忆架构的睡眠与梦境分析开源工具包。通过模拟人类记忆的三层结构（短期记忆、工作记忆、长期记忆），结合多模态睡眠生理信号（EEG、EMG、EOG），自动标注睡眠阶段，挖掘梦境内容模式，帮助研究者建立睡眠生理与主观梦境体验之间的关联模型。

## 核心功能

- **三层记忆引擎**：短期记忆（实时感知）→ 工作记忆（信息整合）→ 长期记忆（知识沉淀）
- **多模态数据导入**：支持 EDF、CSV、JSON 格式的睡眠生理数据
- **睡眠阶段标注**：基于 American Academy of Sleep Medicine (AASM) 标准自动分阶段
- **梦境内容分析**：提取关键词、情感标签、意象类型
- **可视化报告**：生成个人睡眠-梦境分析 PDF 报告
- **数据导出**：支持与 Excel、Notion 等工具联动

## 安装

```bash
pip install three_layer_memory
```

或从源码安装：

```bash
git clone https://github.com/YOUR_USERNAME/three_layer_memory.git
cd three_layer_memory
pip install -e .
```

## 快速开始

```python
from three_layer_memory import SleepAnalyzer

analyzer = SleepAnalyzer()
analyzer.load_eeg("path/to/your/eeg_data.edf")
stages = analyzer.auto_stage()
report = analyzer.generate_report(stages)
report.save("sleep_dream_report.pdf")
```

## 项目结构

```
three_layer_memory/
├── models/         # 三层记忆数据模型
├── core/          # 核心信号处理引擎
├── analyzer.py    # 主分析器
└── utils.py       # 工具函数
```

## 测试

```bash
pytest tests/
```

## 适用场景

- AI Agent 记忆系统研究与开发
- 睡眠医学
- 认知科学
- 个人睡眠追踪爱好者
- AI + 心理学交叉研究

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。
