#!/bin/bash
# Autoflow 定时任务管理脚本
# 提供友好的定时任务创建和管理功能

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${PURPLE}╔══════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║  Autoflow 定时任务管理器                ║${NC}"
echo -e "${PURPLE}║  Scheduled Tasks Manager                  ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════╝${NC}"
echo ""

# 显示帮助
show_help() {
    cat << EOF
用法: $0 <命令> [参数]

命令:
  create <描述>        创建定时任务（支持自然语言）
  list               列出所有任务
  pause <任务ID>      暂停任务
  resume <任务ID>     恢复任务
  cancel <任务ID>     取消任务
  start              启动调度器
  report             生成任务报告
  templates          显示预设模板

示例:
  # 使用自然语言创建任务
  $0 create "每5分钟监控项目进度"
  $0 create "每天早上9点生成日报"
  $0 create "每小时检查系统资源"

  # 管理任务
  $0 list
  $0 pause task_20230316120000
  $0 resume task_20230316120000

  # 启动调度器
  $0 start

预设模板:
  daily-report        每日报告（每天早上9点）
  hourly-monitor       每小时监控
  resource-check      资源检查（每30分钟）
  progress-watch      进度监控（每10分钟）
  cleanup             自动清理（每天凌晨3点）

EOF
}

# 显示预设模板
show_templates() {
    echo -e "${BLUE}预设任务模板:${NC}"
    echo ""
    echo "1. 📊 daily-report"
    echo "   每天早上9点生成项目日报"
    echo "   $0 create --template daily-report"
    echo ""
    echo "2. 🔍 hourly-monitor"
    echo "   每小时监控项目进度"
    echo "   $0 create --template hourly-monitor"
    echo ""
    echo "3. 💻 resource-check"
    echo "   每30分钟检查系统资源"
    echo "   $0 create --template resource-check"
    echo ""
    echo "4. ⏰ progress-watch"
    echo "   每10分钟监控进度"
    echo "   $0 create --template progress-watch"
    echo ""
    echo "5. 🧹 cleanup"
    echo "   每天凌晨3点自动清理"
    echo "   $0 create --template cleanup"
    echo ""
}

# 创建任务
create_task() {
    local description="$1"
    local template="$2"

    if [ -n "$template" ]; then
        case "$template" in
            daily-report)
                description="每天早上9点生成项目日报"
                schedule="0 9 * * *"
                callback="generate_report"
                ;;
            hourly-monitor)
                description="每小时监控项目进度"
                schedule="3600"
                callback="monitor_project"
                ;;
            resource-check)
                description="每30分钟检查系统资源"
                schedule="1800"
                callback="check_resources"
                ;;
            progress-watch)
                description="每10分钟监控进度"
                schedule="600"
                callback="monitor_project"
                ;;
            cleanup)
                description="每天凌晨3点自动清理"
                schedule="0 3 * * *"
                command="python3 scripts/resource-monitor.py --cleanup"
                ;;
            *)
                echo -e "${RED}✗ 未知模板: $template${NC}"
                echo "使用 '$0 templates' 查看可用模板"
                exit 1
                ;;
        esac
    fi

    echo -e "${BLUE}创建定时任务:${NC} $description"
    echo ""

    # 使用 Python 模块创建任务
    python3 - << EOF
import sys
sys.path.insert(0, '.')
from autoflow.scheduler.task_scheduler import TaskScheduler

scheduler = TaskScheduler()

if "$schedule" != "":  # 使用模板
    import json
    task = scheduler.create_task(
        name="$description",
        task_type="report" if "report" in "$description".lower() else "monitor",
        schedule_type="cron" if "*" in "$schedule" else "interval",
        schedule_value="$schedule",
        callback="$callback" if "$callback" else None,
        command="$command" if "$command" else None,
    )
else:
    # 使用自然语言
    task = scheduler.create_from_natural_language("$description")

print(f"\n{task.task_id}")
print(task.name)
print(task.task_type.value)
print(f"{task.schedule_type.value}:{task.schedule_value}")
print(task.next_run.isoformat() if task.next_run else "")
EOF
}

# 列出任务
list_tasks() {
    echo -e "${BLUE}当前定时任务:${NC}"
    echo ""

    python3 -m autoflow.scheduler.task_scheduler list
}

# 暂停任务
pause_task() {
    local task_id="$1"

    if [ -z "$task_id" ]; then
        echo -e "${RED}✗ 请提供任务ID${NC}"
        echo "使用 '$0 list' 查看所有任务"
        exit 1
    fi

    python3 -m autoflow.scheduler.task_scheduler pause "$task_id"
}

# 恢复任务
resume_task() {
    local task_id="$1"

    if [ -z "$task_id" ]; then
        echo -e "${RED}✗ 请提供任务ID${NC}"
        echo "使用 '$0 list' 查看所有任务"
        exit 1
    fi

    python3 -m autoflow.scheduler.task_scheduler resume "$task_id"
}

# 取消任务
cancel_task() {
    local task_id="$1"

    if [ -z "$task_id" ]; then
        echo -e "${RED}✗ 请提供任务ID${NC}"
        echo "使用 '$0 list' 查看所有任务"
        exit 1
    fi

    python3 -m autoflow.scheduler.task_scheduler cancel "$task_id"
}

# 生成报告
show_report() {
    echo -e "${BLUE}任务调度器报告:${NC}"
    echo ""

    python3 -m autoflow.scheduler.task_scheduler report
}

# 启动调度器
start_scheduler() {
    echo -e "${BLUE}启动任务调度器...${NC}"
    echo ""
    echo -e "${GREEN}提示: 按 Ctrl+C 停止调度器${NC}"
    echo ""

    python3 -m autoflow.scheduler.task_scheduler start
}

# 主函数
main() {
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi

    command="$1"
    shift

    case "$command" in
        create)
            if [ "$1" = "--template" ]; then
                create_task "" "$2"
            else
                create_task "$1"
            fi
            ;;
        list|ls)
            list_tasks
            ;;
        pause)
            pause_task "$1"
            ;;
        resume)
            resume_task "$1"
            ;;
        cancel|delete)
            cancel_task "$1"
            ;;
        start|run)
            start_scheduler
            ;;
        report|status)
            show_report
            ;;
        templates|help)
            show_templates
            ;;
        *)
            echo -e "${RED}✗ 未知命令: $command${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
