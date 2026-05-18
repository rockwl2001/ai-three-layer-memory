# -*- coding: utf-8 -*-
"""
agent_memory 安装配置
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="agent-memory",
    version="0.1.0",
    author="Rocky Wang",
    author_email="rocky@example.com",
    description="AI Agent三层记忆系统与梦境系统开源工具包",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rockwl2001/ai-three-layer-memory",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.10",
    install_requires=[
        "flask>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "agent-memory-server=agent_memory.server:main",
        ],
    },
)
