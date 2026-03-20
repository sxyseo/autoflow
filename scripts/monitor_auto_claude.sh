#!/bin/bash
# Auto-Claude实时监控脚本

while true; do
    clear
    echo "🔍 Auto-Claude实时监控"
    echo "====================="
    echo ""

    # 检查进程
    echo "📈 进程状态:"
    gateway_count=$(ps aux | grep -c "openclaw-gateway" || true)
    chrome_count=$(ps aux | grep -c "Google Chrome.*Renderer" || true)
    auto_claude_count=$(ps aux | grep -c "Auto-Claude" || true)

    echo "  - OpenClaw Gateway: $gateway_count"
    echo "  - Chrome渲染进程: $chrome_count"
    echo "  - Auto-Claude进程: $auto_claude_count"

    # 检查内存
    echo ""
    echo "💾 内存使用:"
    memory_used=$(top -l 1 | grep "PhysMem" | awk '{print $2}')
    echo "  - 已使用: $memory_used"

    # 检查磁盘
    echo ""
    echo "💿 磁盘使用:"
    if [ -d ".auto-claude" ]; then
        auto_claude_size=$(du -sh .auto-claude 2>/dev/null | awk '{print $1}')
        echo "  - .auto-claude: $auto_claude_size"
    fi

    if [ -d ".autoflow" ]; then
        autoflow_size=$(du -sh .autoflow 2>/dev/null | awk '{print $1}')
        echo "  - .autoflow: $autoflow_size"
    fi

    # 检查任务状态
    echo ""
    echo "📋 任务状态:"
    if [ -f ".autoflow/tasks/openclaw-autonomy.json" ]; then
        running_tasks=$(grep -c '"status": "in_progress"' .autoflow/tasks/*.json 2>/dev/null || echo "0")
        echo "  - 进行中任务: $running_tasks"
    fi

    echo ""
    echo "⏰ 最后更新: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "按 Ctrl+C 退出"

    sleep 30
done
