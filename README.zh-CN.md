# Autoflow

<div align="center">

**自主软件交付控制平面**

灵感来自 OpenAI 的 "Harness Engineering" 理念和 AI 驱动开发工作流

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md)**

</div>

---

## 目录

- [概述](#概述)
- [理念](#理念)
- [核心概念](#核心概念)
- [架构](#架构)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [配置](#配置)
- [使用方法](#使用方法)
- [高级主题](#高级主题)
- [最佳实践](#最佳实践)
- [故障排除](#故障排除)
- [贡献](#贡献)
- [许可证](#许可证)

## 概述

**Autoflow** 是一个用于自主软件交付的轻量级控制平面。它使 AI 代理能够围绕规格创建、任务分解、实现、审查和维护运行可重复的循环，同时将具体编码工作委托给各种 AI 代理后端。

### Autoflow 的独特之处

与传统开发工具不同，Autoflow 从根本上为 **AI 驱动开发**而构建：

- **状态即真实来源**：每个规格、任务、运行和决策都被显式跟踪
- **确定性提示**：可重用的技能和模板确保一致的代理行为
- **可交换后端**：可互换使用多种 AI 代理
- **后台执行**：代理通过 `tmux` 自主运行，不阻塞工作流
- **自动化门控**：审查、测试和合并检查防止错误提交
- **完全恢复**：每次运行都记录日志且可恢复，确保透明度和可调试性

### 目标：可靠的 AI 自主性

最初的目标**不是**完全自主——而是一个**可靠的 harness**，其中：

- 人类定义目标、边界和验收标准
- AI 在这些约束内自主操作
- 每个变更都经过测试、审查和原子提交
- 失败的迭代自动触发修复，而非人工干预

## 理念

### Harness Engineering

Autoflow 灵感来自 [OpenAI 的 Harness Engineering](https://openai.com/index/harness-engineering/) 理念：**强大的代理来自强大的 harness**。

Harness 提供：
- **评估**：成功和失败的清晰指标
- **编排**：协调的多代理工作流
- **检查点**：可恢复状态和回滚能力
- **契约**：工具使用的明确定义接口

### AI 自完成循环

Autoflow 实现自主开发循环：

```
传统 AI 编码：
人类发现问题 → 人类编写提示 → AI 编写代码 → 人类验证 → (重复)

Autoflow 工作流：
AI 发现问题 → AI 修复 → AI 测试 → AI 提交 → (每 1-2 分钟循环)
```

**关键见解**：
1. **自动化测试是前提**：每次提交必须通过测试
2. **AI 自完成循环**：AI 自主发现、修复、测试和提交
3. **细粒度提交**：小更改（几行）实现安全、快速的迭代
4. **规则层的人工参与，而非执行层**：人类设定边界；AI 处理执行

### 规格驱动开发

Autoflow 应用规格驱动开发原则：

- **规格** 定义意图、约束和验收标准
- **任务** 定义具有依赖关系和状态的工作单元
- **技能** 为每个角色定义可重用的工作流
- **运行** 存储具有完整上下文的具体执行
- **代理** 将逻辑角色映射到具体的 AI 后端

## 核心概念

### 状态层次结构

```
.autoflow/
├── specs/           # 产品意图和约束
│   └── <slug>/
│       ├── SPEC.md              # 需求和约束
│       ├── TASKS.json           # 任务图和状态
│       ├── QA_FIX_REQUEST.md    # 审查发现（markdown）
│       ├── QA_FIX_REQUEST.json  # 审查发现（结构化）
│       └── events.jsonl         # 事件日志
├── tasks/           # 任务定义和状态
├── runs/            # 每次执行的提示、日志、输出
│   └── <timestamp>-<role>-<spec>-<task>/
│       ├── prompt.md            # 发送给代理的完整提示
│       ├── summary.md           # 代理的摘要
│       ├── run.sh               # 执行脚本
│       └── metadata.json        # 运行元数据
├── memory/          # 范围记忆捕获
│   ├── global.md                # 跨规格经验
│   └── specs/
│       └── <slug>.md            # 每个规格的上下文
├── worktrees/       # 每个规格的 git 工作树
└── logs/            # 执行日志
```

### 任务状态工作流

```
todo → in_progress → in_review → done
                   ↓           ↑
              needs_changes    |
                   ↓           |
                blocked ←─────┘
                   ↓
                  todo
```

**有效状态**：
- `todo`：准备开始
- `in_progress`：正在执行
- `in_review`：等待审查
- `done`：已完成并批准
- `needs_changes`：审查发现问题
- `blocked`：等待依赖

### 运行结果

**有效结果**：
- `success`：任务成功完成
- `needs_changes`：已完成但需要修复
- `blocked`：由于依赖无法继续
- `failed`：执行失败

### 技能和角色

Autoflow 将 **技能** 定义为可重用的工作流：

| 技能 | 角色 | 描述 |
|-------|------|-------------|
| `spec-writer` | 规划者 | 将意图转换为结构化规格 |
| `task-graph-manager` | 架构师 | 推导和细化执行图 |
| `implementation-runner` | 实现者 | 执行有界范围的编码切片 |
| `reviewer` | 质量保证 | 运行审查、回归和合并检查 |
| `maintainer` | 运维者 | 问题分类、依赖升级、清理 |

每个技能包括：
- **工作流描述**：逐步过程
- **角色框架**：一致代理行为的模板
- **规则和约束**：代理可以和不可以做什么
- **输出格式**：预期的工件和交接

### 代理协议

Autoflow 支持多种代理协议：

#### CLI 协议 (codex, claude)

```json
{
  "protocol": "cli",
  "command": "claude",
  "args": ["--full-auto"],
  "model_profile": "implementation",
  "memory_scopes": ["global", "spec"],
  "resume": {
    "mode": "subcommand",
    "subcommand": "resume",
    "args": ["--last"]
  }
}
```

#### ACP 协议 (acp-agent)

```json
{
  "protocol": "acp",
  "transport": {
    "type": "stdio",
    "command": "my-agent",
    "args": []
  },
  "prompt_mode": "argv"
}
```

## 架构

### 四层系统

```
┌─────────────────────────────────────────────────────────────┐
│                  第 4 层：治理层                             │
│              审查门控、CI/CD、分支策略                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  第 3 层：执行层                             │
│           规格、角色、代理、提示、工作空间                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  第 2 层：角色层（技能）                     │
│    规格编写器、任务图管理器、实现运行器、审查员、维护者、      │
│                    迭代管理器                                │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                  第 1 层：控制平面                           │
│              状态、配置、记忆、发现                           │
└─────────────────────────────────────────────────────────────┘
```

### 组件图

```
┌──────────────────────────────────────────────────────────────┐
│                      外部编排器                               │
│                  (Cron / 人类 / 自定义)                       │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    Autoflow 控制平面                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  规格    │  │  任务    │  │  运行    │  │  记忆    │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │             │             │             │           │
│       └─────────────┴─────────────┴─────────────┘           │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐    │
│  │                     技能系统                         │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │    │
│  │  │规格编写  │ │任务图    │ │实现运行  │           │    │
│  │  │器        │ │管理器    │ │器        │           │    │
│  │  └──────────┘ └──────────┘ └──────────┘           │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │    │
│  │  │审查员    │ │维护者    │ │迭代      │           │    │
│  │  └──────────┘ └──────────┘ └──────────┘           │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐    │
│  │                  代理注册表                          │    │
│  │  CLI (claude, codex) │ ACP (自定义) │ 编排          │    │
│  └────────────────────────┬────────────────────────────┘    │
└───────────────────────────┼─────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      执行层                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  tmux    │  │  代理    │  │  Git     │  │  工作树  │  │
│  │ 会话     │  │  运行器  │  │  操作    │  │  隔离    │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## 功能特性

### 1. 显式状态管理

开发过程的每个方面都被显式跟踪：

- **规格**：意图、需求、约束、验收标准
- **任务**：具有依赖关系、状态和分配的工作单元
- **运行**：包含提示、输出和元数据的完整执行历史
- **记忆**：跨规格和运行的范围学习捕获
- **事件**：每个规格的事件日志，用于审计和恢复

### 2. 确定性提示组装

Autoflow 通过以下方式确保一致的代理行为：

- **技能定义**：具有清晰步骤的可重用工作流
- **角色模板**：一致代理角色的角色框架
- **上下文注入**：自动包含相关状态、记忆和发现
- **提示版本控制**：每次运行存储完整提示以实现可重现性

### 3. 可交换的代理后端

通过统一协议支持多个 AI 后端：

- **CLI 协议**：用于命令行代理
- **ACP 协议**：用于代理通信协议代理
- **原生继续**：代理特定的恢复机制
- **动态回退**：失败时自动代理选择

### 4. 后台执行

通过 `tmux` 自主操作：

- **非阻塞**：运行在后台执行而不中断工作流
- **可附加**：实时监控运行或稍后查看日志
- **可恢复**：中断运行的原生继续支持
- **资源管理**：每个代理和规格的并发运行限制

### 5. 审查和合并门控

自动化质量检查防止错误提交：

- **结构化发现**：机器可读的 QA 工件，包含位置、严重性和修复
- **基于哈希的批准**：实现哈希必须匹配批准的审查
- **门控执行**：系统在规划更改后阻止实现
- **任务驱动的重试**：结构化发现注入到修复提示中

### 6. 记忆和学习

跨运行积累的智慧：

- **全局记忆**：跨规格的经验和模式
- **规格记忆**：每个规格的上下文和历史
- **策略记忆**：重复障碍的 playbook
- **自动捕获**：从成功运行中提取记忆
- **提示注入**：基于代理配置自动包含上下文

### 7. 工作树隔离

安全的并行开发：

- **每个规格的工作树**：隔离的 git 工作树
- **清洁的主仓库**：主分支保持原始状态
- **原子合并**：仅在批准后合并更改
- **轻松回滚**：失败时恢复工作树

### 8. 持续迭代

计划的自主开发：

- **基于时钟的循环**：检查、提交、调度、推送
- **自动提交**：带有前缀消息的描述性提交
- **验证**：提交前测试和检查
- **进度跟踪**：自动任务状态推进

## 快速开始

### 前提条件

- Python 3.10 或更高版本
- Git
- tmux
- AI 代理后端 (Claude Code、Codex 或自定义)

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-org/autoflow.git
cd autoflow

# （可选）创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 初始化

```bash
# 1. 设置本地状态目录
python3 scripts/autoflow.py init

# 2. 初始化系统配置
python3 scripts/autoflow.py init-system-config

# 3. 复制并自定义代理配置
cp config/agents.example.json .autoflow/agents.json

# 4. 编辑代理配置以添加您的 AI 后端
# 编辑 .autoflow/agents.json 以配置您的代理

# 5. 发现并同步本地/ACP 代理
python3 scripts/autoflow.py sync-agents
```

### 创建您的第一个规格

```bash
python3 scripts/autoflow.py new-spec \
  --slug my-first-project \
  --title "我的第一个 AI 项目" \
  --summary "构建一个令人惊叹的 AI 驱动应用程序"
```

### 生成任务图

```bash
# 让 AI 将您的规格分解为任务
python3 scripts/autoflow.py init-tasks --spec my-first-project

# 查看工作流状态
python3 scripts/autoflow.py workflow-state --spec my-first-project
```

### 开始自主开发

```bash
# 启用持续迭代
python3 scripts/continuous_iteration.py \
  --spec my-first-project \
  --config config/continuous-iteration.example.json \
  --commit-if-dirty \
  --dispatch \
  --push
```

就是这样！Autoflow 现在将：
1. 检查已完成的工作
2. 使用描述性消息提交更改
3. 运行验证测试
4. 调度下一个就绪任务
5. 在后台启动代理
6. 每 2-5 分钟重复一次

### 验证 README 流程

```bash
# 命令层 smoke test
python3 scripts/validate_readme_flow.py --agent codex

# 运行层 smoke test（使用一次性的 dummy ACP agent 和 tmux）
python3 scripts/validate_runtime_loop.py
```

第二条命令会验证：
- `continuous_iteration.py --dispatch` 能创建后台 tmux run
- `scheduler.py run-once --job-type continuous_iteration` 能使用调度配置驱动同一条链路
- active run 记录会被写入状态层，而不是只停留在文档声明

## 配置

### 代理配置 (`.autoflow/agents.json`)

```json
{
  "agents": {
    "claude-impl": {
      "name": "Claude 实现代理",
      "protocol": "cli",
      "command": "claude",
      "args": ["--full-auto"],
      "model_profile": "implementation",
      "tool_profile": "default",
      "memory_scopes": ["global", "spec"],
      "roles": ["implementation-runner", "maintainer"],
      "max_concurrent": 3,
      "resume": {
        "mode": "subcommand",
        "subcommand": "resume",
        "args": ["--last"]
      }
    },
    "codex-spec": {
      "name": "Codex 规格代理",
      "protocol": "cli",
      "command": "codex",
      "args": ["--full-auto"],
      "model_profile": "spec",
      "tool_profile": "spec-tools",
      "memory_scopes": ["global"],
      "roles": ["spec-writer", "task-graph-manager"],
      "max_concurrent": 2
    }
  }
}
```

### 系统配置 (`.autoflow/system.json`)

```json
{
  "memory": {
    "enabled": true,
    "scopes": ["global", "spec", "strategy"],
    "auto_capture": true,
    "global_memory_path": ".autoflow/memory/global.md",
    "spec_memory_dir": ".autoflow/memory/specs",
    "strategy_memory_dir": ".autoflow/memory/strategy"
  },
  "model_profiles": {
    "spec": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.7,
      "max_tokens": 8192
    },
    "implementation": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.3,
      "max_tokens": 16384
    },
    "review": {
      "model": "claude-opus-4-6",
      "temperature": 0.2,
      "max_tokens": 16384
    }
  },
  "tool_profiles": {
    "default": {
      "allowed_tools": ["read", "write", "edit", "bash", "search"],
      "denied_tools": []
    },
    "spec-tools": {
      "allowed_tools": ["read", "write", "edit", "search"],
      "denied_tools": ["bash"]
    }
  },
  "acp_registry": {
    "enabled": true,
    "discovery_paths": [
      "/usr/local/bin/acp-agents/*",
      "~/.local/share/acp-agents/*"
    ]
  }
}
```

### 持续迭代配置

```json
{
  "spec": "my-first-project",
  "role_agents": {
    "spec-writer": "codex-spec",
    "task-graph-manager": "codex-spec",
    "implementation-runner": "claude-impl",
    "reviewer": "claude-review",
    "maintainer": "claude-impl"
  },
  "verify_commands": [
    "python3 -m pytest tests/ -v",
    "python3 scripts/ci_check.sh"
  ],
  "commit": {
    "enabled": true,
    "message_prefix": "autoflow:",
    "push": true,
    "require_active_run": false
  },
  "dispatch": {
    "enabled": true,
    "max_concurrent_runs": 5,
    "dispatch_interval_seconds": 120
  },
  "retry_policy": {
    "max_attempts": 3,
    "require_fix_request": true,
    "backoff_multiplier": 2
  }
}
```

### 调度器配置 (`config/scheduler_config.json`)

`continuous_iteration` job 需要显式指定要驱动的 spec：

```json
{
  "jobs": {
    "continuous_iteration": {
      "enabled": true,
      "cron": "*/5 * * * *",
      "args": {
        "spec": "my-first-project",
        "config": "config/continuous-iteration.example.json",
        "dispatch": true,
        "commit_if_dirty": false,
        "push": false
      }
    }
  }
}
```

## 使用方法

### 基本命令

#### 规格管理

```bash
# 创建新规格
python3 scripts/autoflow.py new-spec \
  --slug <spec-slug> \
  --title "<title>" \
  --summary "<summary>"

# 更新现有规格
python3 scripts/autoflow.py update-spec --slug <spec-slug>

# 查看规格详情
python3 scripts/autoflow.py show-spec --slug <spec-slug>
```

#### 任务管理

```bash
# 为规格初始化任务
python3 scripts/autoflow.py init-tasks --spec <spec-slug>

# 显示工作流状态
python3 scripts/autoflow.py workflow-state --spec <spec-slug>

# 更新任务状态
python3 scripts/autoflow.py update-task \
  --spec <spec-slug> \
  --task <task-id> \
  --status <status>

# 显示任务历史
python3 scripts/autoflow.py task-history \
  --spec <spec-slug> \
  --task <task-id>
```

#### 运行管理

```bash
# 创建新运行
python3 scripts/autoflow.py new-run \
  --spec <spec-slug> \
  --role <role> \
  --agent <agent-name> \
  --task <task-id>

# 在 tmux 中启动运行
scripts/tmux-start.sh .autoflow/runs/<run-id>/run.sh

# 附加到正在运行的会话
tmux attach -t autoflow-run-<timestamp>

# 完成运行
python3 scripts/autoflow.py complete-run \
  --run <run-id> \
  --result <success|needs_changes|blocked|failed> \
  --summary "<summary>"
```

#### 记忆和学习

```bash
# 显示范围记忆
python3 scripts/autoflow.py show-memory --scope global
python3 scripts/autoflow.py show-memory --scope spec --spec <spec-slug>

# 从已完成的运行中捕获记忆
python3 scripts/autoflow.py capture-memory --run <run-id>

# 添加规划者笔记
python3 scripts/autoflow.py add-planner-note \
  --spec <spec-slug> \
  --note "<note>"
```

#### 工作树管理

```bash
# 创建或刷新每个规格的工作树
python3 scripts/autoflow.py create-worktree --spec <spec-slug>

# 强制重建工作树
python3 scripts/autoflow.py create-worktree --spec <spec-slug> --force
```

## 高级主题

### 审查门控系统

Autoflow 实现基于哈希的审查批准：

```bash
# 审查员生成发现
python3 scripts/autoflow.py show-fix-request --spec <spec-slug>

# 实现哈希存储在 review_state.json 中
# 系统在审查批准之前阻止实现
cat .autoflow/specs/<slug>/review_state.json
```

### 结构化发现

审查发现是机器可读的：

```json
{
  "findings": [
    {
      "file": "src/auth.py",
      "line": 42,
      "end_line": 45,
      "severity": "error",
      "category": "security",
      "title": "缺少输入验证",
      "body": "JWT 令牌在使用前未验证",
      "suggested_fix": "添加验证：validate_jwt(token)",
      "source_run": "20260307T123456Z-reviewer-feature-auth-T3"
    }
  ]
}
```

发现自动注入到修复提示中，以实现任务驱动的重试。

### 原生继续

支持原生继续的代理无缝恢复：

```bash
# Codex 使用 --last 标志恢复
"resume": {
  "mode": "subcommand",
  "subcommand": "resume",
  "args": ["--last"]
}

# Claude 使用基于会话的继续
"resume": {
  "mode": "session",
  "session_file": ".claude_session"
}
```

### 多代理编排

并行运行多个代理：

```bash
# 配置多个实现代理
# 在 .autoflow/agents.json 中：
{
  "agents": {
    "claude-impl-1": {"max_concurrent": 3},
    "claude-impl-2": {"max_concurrent": 3},
    "codex-impl": {"max_concurrent": 2}
  }
}

# 系统将调度任务到可用的代理
# 遵守 max_concurrent 限制
```

### 自定义技能

定义您自己的技能：

```bash
# 创建技能目录
mkdir -p skills/my-custom-skill

# 编写 SKILL.md
cat > skills/my-custom-skill/SKILL.md << 'EOF'
# 自定义技能

## 描述
此技能执行 X、Y、Z。

## 工作流
1. 第一步
2. 第二步
3. 第三步

## 规则
- 始终验证输入
- 永不修改配置文件
- 完成前运行测试

## 输出格式
- artifact1.md：工件描述
- artifact2.json：结构化数据
EOF

# 在 agents.json 中使用
"roles": ["my-custom-skill"]
```

## 最佳实践

### 1. 从强大的基础开始

- 预先投资全面的测试覆盖
- 为每个任务定义清晰的验收标准
- 在自主操作之前设置 CI/CD 门控

### 2. 定义清晰的边界

- 指定 AI 可以和不可以自主做什么
- 设置资源限制（时间、内存、API 调用）
- 定义人工干预的升级触发器

### 3. 信任但验证

- 让 AI 在边界内自主操作
- 定期监控输出，而不是持续监控
- 仅在违反边界时进行干预

### 4. 拥抱快速迭代

- 小而专注的更改 > 大型 PR
- 快速反馈循环 > 完美规划
- 自动恢复 > 手动调试

### 5. 学习和适应

- 每周审查 AI 决策
- 根据模式更新边界
- 将学到的经验整合到记忆中

## 故障排除

### 代理运行停滞或挂起

```bash
# 检查活动的 tmux 会话
tmux ls

# 附加到特定会话以进行调试
tmux attach -t autoflow-run-<timestamp>

# 终止停滞的会话
tmux kill-session -t autoflow-run-<timestamp>
```

### 任务持续失败

```bash
# 检查任务历史的模式
python3 scripts/autoflow.py task-history --spec <spec> --task <task-id>

# 检查是否存在修复请求
python3 scripts/autoflow.py show-fix-request --spec <spec>

# 查看任务的最近运行
ls -lt .autoflow/runs/ | grep <task-id>

# 手动推进被阻塞的任务
python3 scripts/autoflow.py update-task \
  --spec <spec> \
  --task <task-id> \
  --status todo
```

### 配置问题

```bash
# 验证代理配置
python3 scripts/autoflow.py validate-config

# 测试代理可用性
python3 scripts/autoflow.py test-agent --agent <agent-name>

# 同步已发现的代理
python3 scripts/autoflow.py sync-agents --overwrite
```

### 记忆和状态损坏

```bash
# 重置特定任务状态
python3 scripts/autoflow.py reset-task --spec <spec> --task <task-id>

# 清除停滞的运行
python3 scripts/autoflow.py cleanup-runs --spec <spec>

# 重建工作树
python3 scripts/autoflow.py create-worktree --spec <spec> --force
```

## 贡献

我们欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

<div align="center">

**[⬆ 返回顶部](#autoflow)**

由 Autoflow 社区用 ❤️ 制作

</div>
