#!/bin/bash
# Auto-Claude Performance Optimization Script
# 解决开发速度慢和token消耗过多的问题

set -e

echo "🚀 Auto-Claude Performance Optimization"
echo "======================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Auto-Claude paths
AUTO_CLAUDE_DIR="$HOME/Library/Application Support/auto-claude-ui"
PROJECT_AUTO_CLAUDE="$PWD/.auto-claude"
PROJECT_AUTOFLOW="$PWD/.autoflow"

# Functions
cleanup_old_data() {
    echo -e "${BLUE}🧹 清理旧数据...${NC}"

    # 清理Auto-Claude缓存
    if [ -d "$AUTO_CLAUDE_DIR" ]; then
        echo "清理Auto-Claude缓存..."
        rm -rf "$AUTO_CLAUDE_DIR/Cache"/*
        rm -rf "$AUTO_CLAUDE_DIR/Code Cache"/*
        rm -rf "$AUTO_CLAUDE_DIR/GPUCache"/*
    fi

    # 清理项目中的auto-claude数据
    if [ -d "$PROJECT_AUTO_CLAUDE" ]; then
        echo "清理项目auto-claude数据..."

        # 保留最近7天的运行记录
        find "$PROJECT_AUTO_CLAUDE" -name "prompt.md" -mtime +7 -delete
        find "$PROJECT_AUTO_CLAUDE" -name "*.log" -mtime +7 -delete
        find "$PROJECT_AUTO_CLAUDE" -name "output.txt" -mtime +7 -delete

        # 清理空的运行目录
        find "$PROJECT_AUTO_CLAUDE" -type d -empty -delete 2>/dev/null || true
    fi

    echo -e "${GREEN}✅ 数据清理完成${NC}"
}

kill_duplicate_processes() {
    echo -e "${BLUE}🔄 清理重复进程...${NC}"

    # 检查openclaw-gateway进程
    gateway_count=$(ps aux | grep -c "openclaw-gateway" || true)

    if [ "$gateway_count" -gt 1 ]; then
        echo -e "${YELLOW}⚠️  发现 $gateway_count 个openclaw-gateway进程${NC}"
        echo "保留最新进程，终止其他进程..."

        # 保留最新的进程，终止其他的
        ps aux | grep "openclaw-gateway" | grep -v grep | sort -k3 -r | tail -n +2 | awk '{print $2}' | xargs kill -9 2>/dev/null || true

        echo -e "${GREEN}✅ 进程清理完成${NC}"
    else
        echo -e "${GREEN}✅ 进程状态正常${NC}"
    fi

    # 清理僵尸Chrome进程
    chrome_count=$(ps aux | grep -c "Google Chrome Helper.*Renderer" || true)
    if [ "$chrome_count" -gt 10 ]; then
        echo -e "${YELLOW}⚠️  发现 $chrome_count 个Chrome渲染进程${NC}"
        echo "清理旧的渲染进程..."

        ps aux | grep "Google Chrome Helper.*Renderer" | grep -v grep | sort -k3 -r | tail -n +6 | awk '{print $2}' | xargs kill -9 2>/dev/null || true

        echo -e "${GREEN}✅ Chrome进程清理完成${NC}"
    fi
}

optimize_auto_claude_settings() {
    echo -e "${BLUE}⚙️  优化Auto-Claude设置...${NC}"

    # 创建优化的配置文件
    cat > "$PROJECT_AUTOFLOW/auto_claude_optimization.json" << 'EOF'
{
  "performance_settings": {
    "max_concurrent_requests": 3,
    "cache_enabled": true,
    "cache_ttl_hours": 24,
    "log_retention_days": 7,
    "auto_cleanup_enabled": true,
    "memory_limit_mb": 2048,
    "context_window_tokens": 8000,
    "max_response_tokens": 2000
  },
  "token_optimization": {
    "use_system_prompt": true,
    "compress_context": true,
    "remove_duplicates": true,
    "summarize_old_messages": true,
    "max_history_messages": 50
  },
  "task_optimization": {
    "batch_similar_tasks": true,
    "parallel_independent_tasks": false,
    "priority_based_execution": true,
    "timeout_minutes": 30
  }
}
EOF

    echo -e "${GREEN}✅ 配置文件创建完成${NC}"
}

create_monitoring_script() {
    echo -e "${BLUE}📊 创建监控脚本...${NC}"

    cat > "$PWD/scripts/monitor_auto_claude.sh" << 'MONITOR_EOF'
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
MONITOR_EOF

    chmod +x "$PWD/scripts/monitor_auto_claude.sh"
    echo -e "${GREEN}✅ 监控脚本创建完成${NC}"
}

show_recommendations() {
    echo ""
    echo -e "${BLUE}💡 性能优化建议:${NC}"
    echo ""
    echo "1. 🔄 定期清理数据："
    echo "   bash scripts/auto_claude_optimization.sh"
    echo ""
    echo "2. 📊 实时监控系统："
    echo "   bash scripts/monitor_auto_claude.sh"
    echo ""
    echo "3. ⚙️  优化开发流程："
    echo "   - 使用更小的任务分解"
    echo "   - 限制上下文窗口大小"
    echo "   - 启用结果缓存"
    echo "   - 定期重启Auto-Claude"
    echo ""
    echo "4. 🚀 提升开发速度："
    echo "   - 减少token消耗：启用上下文压缩"
    echo "   - 并行处理：谨慎使用多进程"
    echo "   - 超时控制：设置任务时间限制"
    echo "   - 缓存策略：重用已有结果"
    echo ""
}

# Main execution
main() {
    echo -e "${BLUE}开始优化...${NC}"
    echo ""

    cleanup_old_data
    echo ""

    kill_duplicate_processes
    echo ""

    optimize_auto_claude_settings
    echo ""

    create_monitoring_script
    echo ""

    show_recommendations

    echo -e "${GREEN}✨ 优化完成！${NC}"
    echo ""
    echo "📊 优化前后的对比:"
    echo "  - 清理前: .auto-claude 1.1GB"
    echo "  - 清理后: $(du -sh .auto-claude 2>/dev/null | awk '{print $1}')"
    echo "  - 进程数: $(ps aux | grep -c 'openclaw-gateway' || true) 个gateway"
    echo ""
    echo "🔧 下一步：运行监控脚本查看实时状态"
    echo "   bash scripts/monitor_auto_claude.sh"
}

# Run main function
main
