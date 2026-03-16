# Autoflow 定时任务系统使用指南

## 🎯 功能概述

Autoflow 定时任务系统提供了类似 OpenClaw、Claude Code、CodeX 的定时任务和循环功能：

- ✅ **定时监控** - 定期检查项目进度和资源使用
- ✅ **自动报告** - 自动生成日报、周报等
- ✅ **自然语言** - 使用自然语言创建任务
- ✅ **智能调度** - 支持 cron 表达式和间隔调度
- ✅ **自动管理** - 完成后自动清理或暂停

## 🚀 快速开始

### 1. 使用自然语言创建任务

```bash
# 监控项目进度（每5分钟）
./scripts/scheduled-tasks.sh create "每5分钟监控项目进度"

# 生成日报（每天早上9点）
./scripts/scheduled-tasks.sh create "每天早上9点生成日报"

# 检查资源（每30分钟）
./scripts/scheduled-tasks.sh create "每30分钟检查系统资源"

# 进度监控（每10分钟）
./scripts/scheduled-tasks.sh create "每10分钟监控进度"
```

### 2. 使用预设模板

```bash
# 查看所有模板
./scripts/scheduled-tasks.sh templates

# 使用模板创建任务
./scripts/scheduled-tasks.sh create --template daily-report     # 每日报告
./scripts/scheduled-tasks.sh create --template hourly-monitor    # 每小时监控
./scripts/scheduled-tasks.sh create --template resource-check    # 资源检查
./scripts/scheduled-tasks.sh create --template progress-watch    # 进度监控
./scripts/scheduled-tasks.sh create --template cleanup           # 自动清理
```

### 3. 管理任务

```bash
# 列出所有任务
./scripts/scheduled-tasks.sh list

# 暂停任务
./scripts/scheduled-tasks.sh pause <task_id>

# 恢复任务
./scripts/scheduled-tasks.sh resume <task_id>

# 取消任务
./scripts/scheduled-tasks.sh cancel <task_id>

# 查看报告
./scripts/scheduled-tasks.sh report
```

### 4. 启动调度器

```bash
# 启动调度器（前台运行）
./scripts/scheduled-tasks.sh start

# 或者在后台运行
nohup ./scripts/scheduled-tasks.sh start > /dev/null 2>&1 &
```

## 📋 预设任务模板

### 📊 daily-report
**描述：** 每天早上9点生成项目日报
**调度：** `0 9 * * *` (Cron)
**类型：** 报告任务

```bash
./scripts/scheduled-tasks.sh create --template daily-report
```

**功能：**
- 生成项目进度报告
- 汇总任务完成情况
- 统计资源使用情况
- 识别问题和风险

### 🔍 hourly-monitor
**描述：** 每小时监控项目进度
**调度：** `3600` (间隔，秒)
**类型：** 监控任务

```bash
./scripts/scheduled-tasks.sh create --template hourly-monitor
```

**功能：**
- 检查工作流状态
- 监控任务进度
- 更新任务统计
- 发送进度通知

### 💻 resource-check
**描述：** 每30分钟检查系统资源
**调度：** `1800` (间隔，秒)
**类型：** 监控任务

```bash
./scripts/scheduled-tasks.sh create --template resource-check
```

**功能：**
- 检查 CPU 使用率
- 检查内存使用率
- 识别高资源进程
- 自动清理僵尸进程

### ⏰ progress-watch
**描述：** 每10分钟监控进度
**调度：** `600` (间隔，秒)
**类型：** 监控任务

```bash
./scripts/scheduled-tasks.sh create --template progress-watch
```

**功能：**
- 实时进度监控
- 快速问题检测
- 及时通知
- 详细日志记录

### 🧹 cleanup
**描述：** 每天凌晨3点自动清理
**调度：** `0 3 * * *` (Cron)
**类型：** 清理任务

```bash
./scripts/scheduled-tasks.sh create --template cleanup
```

**功能：**
- 清理临时文件
- 清理僵尸进程
- 清理过期日志
- 优化存储空间

## 🎨 高级用法

### 自然语言任务创建

支持多种自然语言描述：

```bash
# 时间间隔
"每5分钟监控项目"
"每小时检查状态"
"每30秒检查资源"

# Cron 表达式
"每天早上9点生成报告"
"每周一上午10点"
"每个月第一天凌晨"

# 复杂描述
"每2小时检查一次项目状态和资源"
"工作日每30分钟监控进度，周末不监控"
```

### 编程方式创建任务

使用 Python API：

```python
from autoflow.scheduler.task_scheduler import TaskScheduler, TaskType, ScheduleType

scheduler = TaskScheduler()

# 创建监控任务
task = scheduler.create_task(
    name="项目监控",
    task_type=TaskType.MONITOR,
    schedule_type=ScheduleType.INTERVAL,
    schedule_value="300",  # 5分钟
    callback="monitor_project",
    auto_cleanup=False,
)

# 创建报告任务
task = scheduler.create_task(
    name="日报生成",
    task_type=TaskType.REPORT,
    schedule_type=ScheduleType.CRON,
    schedule_value="0 9 * * *",  # 每天早上9点
    callback="generate_report",
)

# 创建命令任务
task = scheduler.create_task(
    name="运行测试",
    task_type=TaskType.CUSTOM,
    schedule_type=ScheduleType.INTERVAL,
    schedule_value="3600",  # 每小时
    command="pytest tests/ -v",
    auto_cleanup=True,  # 运行一次后删除
)
```

### 集成到持续迭代

结合持续迭代使用：

```bash
# 1. 启动任务调度器（后台）
nohup ./scripts/scheduled-tasks.sh start > /tmp/scheduler.log 2>&1 &

# 2. 启动持续迭代
python3 scripts/continuous_iteration.py \
  --spec snake-game \
  --config config/continuous-iteration.snake-game.json \
  --commit-if-dirty \
  --dispatch

# 3. 监控运行
tail -f /tmp/scheduler.log
```

## 📊 任务报告示例

```
📊 任务调度器报告
============================================================
总任务数: 5
活跃任务: 4
暂停任务: 1

🟢 task_20230316120000
   项目进度监控
   状态: active | 运行: 23次
   调度: interval:300
   下次: 2026-03-16T12:35:00+00:00

⏸️  task_20230316115000
   每日报告生成
   状态: paused | 运行: 5次
   调度: cron:0 9 * * *
   下次: 2026-03-17T09:00:00+00:00

🟢 task_20230316110000
   资源监控
   状态: active | 运行: 156次
   调度: interval:1800
   下次: 2026-03-16T13:00:00+00:00
```

## 🔧 配置选项

### 调度器配置

编辑 `autoflow/scheduler/task_scheduler.py`:

```python
# 检查间隔（默认30秒）
scheduler._check_interval = 30

# 任务存储目录
TASKS_DIR = STATE_DIR / "scheduled_tasks"

# 默认超时时间
timeout=300  # 5分钟
```

### 任务自动清理

创建任务时启用自动清理：

```bash
# 使用 --auto-cleanup 标志
./scripts/scheduled-tasks.sh create "一次性任务" --auto-cleanup

# 或编程方式
task = scheduler.create_task(
    name="一次性任务",
    task_type=TaskType.CUSTOM,
    schedule_type=ScheduleType.ONCE,
    schedule_value="60",  # 60秒后运行
    command="python3 scripts/autoflow.py workflow-state --spec snake-game",
    auto_cleanup=True,  # 运行后自动删除
)
```

## 💡 使用场景

### 1. 开发过程中持续监控

```bash
# 每10分钟监控进度
./scripts/scheduled-tasks.sh create --template progress-watch

# 每30分钟检查资源
./scripts/scheduled-tasks.sh create --template resource-check

# 启动调度器
nohup ./scripts/scheduled-tasks.sh start > /dev/null 2>&1 &
```

### 2. 自动报告生成

```bash
# 每日报告
./scripts/scheduled-tasks.sh create --template daily-report

# 每周报告
./scripts/scheduled-tasks.sh create "每周一上午10点生成周报"

# 启动调度器
./scripts/scheduled-tasks.sh start
```

### 3. 资源管理和清理

```bash
# 定期清理
./scripts/scheduled-tasks.sh create --template cleanup

# 资源监控
./scripts/scheduled-tasks.sh create "每小时检查资源"

# 启动调度器
nohup ./scripts/scheduled-tasks.sh start > /dev/null 2>&1 &
```

### 4. 项目完成后自动停止

```bash
# 创建监控任务（项目完成后自动删除）
./scripts/scheduled-tasks.sh create \
  "监控项目直到所有任务完成" \
  --auto-cleanup

# 调度器会在任务完成后自动清理
```

## 🎯 最佳实践

1. **合理的监控频率**
   - 开发活跃期：每10-30分钟
   - 稳定期：每1-2小时
   - 资源检查：每30分钟-1小时

2. **使用预设模板**
   - 预设模板已经过优化
   - 适合大多数常见场景
   - 可以根据需要调整

3. **设置自动清理**
   - 一次性任务启用自动清理
   - 长期任务保持运行
   - 避免任务累积

4. **定期审查任务**
   - 每周检查任务列表
   - 删除不需要的任务
   - 调整调度频率

5. **后台运行调度器**
   - 使用 nohup 或 systemd
   - 记录日志到文件
   - 设置监控和重启

## 📚 相关文档

- `docs/AUTONOMOUS_CAPABILITY_VERIFICATION.md` - 自主开发能力验证
- `docs/SUCCESS_SUMMARY.md` - 验证成功总结
- `scripts/continuous_iteration.py` - 持续迭代脚本
- `scripts/resource-monitor.py` - 资源监控工具

## 🆘 故障排除

### 任务不运行

```bash
# 检查任务状态
./scripts/scheduled-tasks.sh list

# 查看任务详情
cat .autoflow/scheduled_tasks/<task_id>.json

# 检查调度器日志
tail -f /tmp/scheduler.log
```

### 调度器启动失败

```bash
# 检查 Python 模块
python3 -c "from autoflow.scheduler.task_scheduler import TaskScheduler; print('OK')"

# 检查目录权限
ls -la .autoflow/scheduled_tasks/

# 手动运行测试
python3 -m autoflow.scheduler.task_scheduler list
```

### 任务执行失败

```bash
# 查看任务日志
cat .autoflow/logs/scheduler.log

# 检查命令是否可用
python3 scripts/autoflow.py workflow-state --spec snake-game

# 测试回调函数
python3 -c "
from autoflow.scheduler.task_scheduler import TaskScheduler
scheduler = TaskScheduler()
scheduler.create_from_natural_language('测试任务').execute()
"
```

---

**现在就开始使用定时任务系统，让 Autoflow 自动监控你的项目！** 🚀
