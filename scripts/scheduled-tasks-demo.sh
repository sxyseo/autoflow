#!/bin/bash
# Autoflow 定时任务系统演示

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}╔══════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}║  Autoflow 定时任务系统演示             ║${NC}"
echo -e "${PURPLE}║  Scheduled Tasks System Demo            ║${NC}"
echo -e "${PURPLE}╚══════════════════════════════════════════╝${NC}"
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 演示步骤
DEMO_STEP=0

demo_step() {
    DEMO_STEP=$((DEMO_STEP + 1))
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  演示 $DEMO_STEP: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

error() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# ============================================================================
# 演示 1: 显示帮助和模板
# ============================================================================
demo_step "查看帮助和预设模板"

echo "显示帮助信息..."
./scripts/scheduled-tasks.sh 2>&1 | head -30

echo ""
echo "显示预设模板..."
./scripts/scheduled-tasks.sh templates

success "帮助和模板显示完成"

# ============================================================================
# 演示 2: 使用自然语言创建任务
# ============================================================================
demo_step "使用自然语言创建定时任务"

echo "创建任务示例："
echo ""

# 示例 1: 监控任务
echo "1. 创建监控任务（每5分钟）"
echo "   命令: ./scripts/scheduled-tasks.sh create \"每5分钟监控项目\""
echo ""

# 示例 2: 报告任务
echo "2. 创建报告任务（每天早上9点）"
echo "   命令: ./scripts/scheduled-tasks.sh create \"每天早上9点生成日报\""
echo ""

# 示例 3: 资源任务
echo "3. 创建资源检查任务（每30分钟）"
echo "   命令: ./scripts/scheduled-tasks.sh create \"每30分钟检查系统资源\""
echo ""

success "自然语言任务创建说明完成"

# ============================================================================
# 演示 3: 使用预设模板创建任务
# ============================================================================
demo_step "使用预设模板创建任务"

echo "使用模板创建任务..."
echo ""

# 创建资源监控任务
echo "创建资源监控任务..."
python3 - <<'PYEOF'
import sys
sys.path.insert(0, '.')
from autoflow.scheduler.task_scheduler import TaskScheduler

scheduler = TaskScheduler()

# 创建一个演示任务
task = scheduler.create_task(
    name="演示任务 - 资源监控",
    task_type="monitor",
    schedule_type="interval",
    schedule_value="300",  # 5分钟
    callback="check_resources",
)

print(f"✓ 任务创建成功!")
print(f"  ID: {task.task_id}")
print(f"  名称: {task.name}")
print(f"  类型: {task.task_type.value}")
print(f"  调度: {task.schedule_type.value}:{task.schedule_value}")
print(f"  下次运行: {task.next_run}")
PYEOF

echo ""
success "预设模板任务创建完成"

# ============================================================================
# 演示 4: 列出和管理任务
# ============================================================================
demo_step "列出和管理任务"

echo "列出所有任务..."
echo ""

./scripts/scheduled-tasks.sh list 2>&1 | head -40

echo ""
echo "任务管理命令："
echo "  • 暂停任务: ./scripts/scheduled-tasks.sh pause <task_id>"
echo "  • 恢复任务: ./scripts/scheduled-tasks.sh resume <task_id>"
echo "  • 取消任务: ./scripts/scheduled-tasks.sh cancel <task_id>"
echo ""

success "任务管理说明完成"

# ============================================================================
# 演示 5: 生成报告
# ============================================================================
demo_step "生成任务调度器报告"

echo "生成调度器报告..."
echo ""

./scripts/scheduled-tasks.sh report 2>&1 | head -50

echo ""
success "报告生成完成"

# ============================================================================
# 演示 6: 实际运行示例
# ============================================================================
demo_step "实际运行示例"

echo "模拟任务执行..."
echo ""

python3 - <<'PYEOF'
import sys
import asyncio
sys.path.insert(0, '.')

async def demo():
    from autoflow.scheduler.task_scheduler import TaskScheduler, TaskType, ScheduleType

    scheduler = TaskScheduler()

    # 创建几个演示任务
    tasks = [
        scheduler.create_task(
            name="项目监控",
            task_type=TaskType.MONITOR,
            schedule_type=ScheduleType.INTERVAL,
            schedule_value="300",
            callback="monitor_project",
        ),
        scheduler.create_task(
            name="日报生成",
            task_type=TaskType.REPORT,
            schedule_type=ScheduleType.CRON,
            schedule_value="0 9 * * *",
            callback="generate_report",
        ),
        scheduler.create_task(
            name="资源检查",
            task_type=TaskType.MONITOR,
            schedule_type=ScheduleType.INTERVAL,
            schedule_value="1800",
            callback="check_resources",
        ),
    ]

    print("创建的任务:")
    for task in tasks:
        status = "🟢 活跃" if task.enabled else "⏸️  暂停"
        print(f"  {status} {task.task_id}")
        print(f"     名称: {task.name}")
        print(f"     类型: {task.task_type.value}")
        print(f"     调度: {task.schedule_type.value}:{task.schedule_value}")
        print()

    # 演示执行一次
    print("演示任务执行:")
    for task in tasks[:1]:  # 只执行第一个
        print(f"  执行: {task.name}")
        result = task.execute()
        if result["success"]:
            print(f"    ✓ 成功")
        else:
            print(f"    ✗ 失败: {result.get('error', 'Unknown')}")

asyncio.run(demo())
PYEOF

success "实际运行示例完成"

# ============================================================================
# 总结
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  演示完成！                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}📚 详细文档:${NC}"
echo "  • docs/SCHEDULED_TASKS_GUIDE.md"
echo ""

echo -e "${BLUE}🚀 快速开始:${NC}"
echo "  # 使用自然语言创建任务"
echo "  ./scripts/scheduled-tasks.sh create \"每5分钟监控项目\""
echo ""
echo "  # 使用预设模板"
echo "  ./scripts/scheduled-tasks.sh create --template daily-report"
echo ""
echo "  # 列出所有任务"
echo "  ./scripts/scheduled-tasks.sh list"
echo ""
echo "  # 启动调度器"
echo "  ./scripts/scheduled-tasks.sh start"
echo ""

echo -e "${BLUE}💡 常见使用场景:${NC}"
echo "  1. 开发过程中持续监控"
echo "  2. 自动报告生成"
echo "  3. 资源管理和清理"
echo "  4. 项目完成后自动停止"
echo ""

echo -e "${PURPLE}Autoflow 定时任务系统已就绪！${NC}"
echo ""
