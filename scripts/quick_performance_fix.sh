#!/bin/bash
# 🚀 Auto-Claude快速性能修复脚本
# 当发现Auto-Claude运行缓慢时，立即运行此脚本

echo "🔥 Auto-Claude 快速性能修复"
echo "============================"
echo ""

# 检查是否需要管理员权限
if [ "$1" != "--skip-warning" ]; then
    echo "⚠️  此脚本将："
    echo "  1. 完全关闭Auto-Claude和相关进程"
    echo "  2. 清理所有缓存"
    echo "  3. 优化系统设置"
    echo "  4. 提供重启建议"
    echo ""
    read -p "继续吗？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 已取消"
        exit 1
    fi
fi

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔄 步骤 1/5: 关闭所有Auto-Claude相关进程${NC}"

# 关闭Auto-Claude
echo "关闭 Auto-Claude.app..."
killall "Auto-Claude" 2>/dev/null || echo "  (Auto-Claude未运行)"

# 关闭Chrome（OpenClaw使用）
echo "关闭 Google Chrome..."
killall "Google Chrome" 2>/dev/null || echo "  (Chrome未运行)"

# 关闭OpenClaw Gateway
echo "关闭 OpenClaw Gateway..."
killall openclaw-gateway 2>/dev/null || echo "  (Gateway未运行)"

# 等待进程完全关闭
sleep 3

echo -e "${GREEN}✅ 所有进程已关闭${NC}"
echo ""

echo -e "${BLUE}🧹 步骤 2/5: 清理缓存和临时文件${NC}"

# Auto-Claude缓存
AUTO_CLAUDE_CACHE="$HOME/Library/Application Support/auto-claude-ui"
if [ -d "$AUTO_CLAUDE_CACHE" ]; then
    echo "清理 Auto-Claude 缓存..."
    rm -rf "$AUTO_CLAUDE_CACHE/Cache/"* 2>/dev/null || true
    rm -rf "$AUTO_CLAUDE_CACHE/Code Cache/"* 2>/dev/null || true
    rm -rf "$AUTO_CLAUDE_CACHE/GPUCache/"* 2>/dev/null || true
    rm -rf "$AUTO_CLAUDE_CACHE/DawnGraphiteCache/"* 2>/dev/null || true
    rm -rf "$AUTO_CLAUDE_CACHE/DawnWebGPUCache/"* 2>/dev/null || true
    echo -e "${GREEN}✅ Auto-Claude缓存已清理${NC}"
fi

# 项目缓存
if [ -d ".auto-claude" ]; then
    echo "清理项目缓存..."
    # 删除7天前的日志
    find .auto-claude -name "*.log" -mtime +7 -delete 2>/dev/null || true
    # 删除大的prompt文件
    find .auto-claude -name "prompt.md" -size +1M -delete 2>/dev/null || true
    # 删除临时文件
    find .auto-claude -name "tmp.*" -mtime +1 -delete 2>/dev/null || true
    echo -e "${GREEN}✅ 项目缓存已清理${NC}"
fi

echo ""

echo -e "${BLUE}⚙️  步骤 3/5: 优化系统设置${NC}"

# 清理Python缓存
echo "清理Python缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 清理node_modules缓存（如果存在）
if [ -d "node_modules/.cache" ]; then
    echo "清理Node.js缓存..."
    rm -rf node_modules/.cache 2>/dev/null || true
fi

echo -e "${GREEN}✅ 系统设置已优化${NC}"
echo ""

echo -e "${BLUE}📊 步骤 4/5: 检查系统状态${NC}"

# 检查内存
echo "内存使用情况:"
top -l 1 | grep "PhysMem"

# 检查磁盘
echo ""
echo "磁盘使用情况:"
if [ -d ".auto-claude" ]; then
    auto_claude_size=$(du -sh .auto-claude 2>/dev/null | awk '{print $1}')
    echo "  .auto-claude: $auto_claude_size"
fi

if [ -d ".autoflow" ]; then
    autoflow_size=$(du -sh .autoflow 2>/dev/null | awk '{print $1}')
    echo "  .autoflow: $autoflow_size"
fi

# 检查是否还有残留进程
echo ""
echo "残留进程检查:"
remaining_processes=$(ps aux | grep -E "Auto-Claude|openclaw-gateway|Google Chrome" | grep -v grep | wc -l | tr -d ' ')
echo "  残留进程数: $remaining_processes"

if [ "$remaining_processes" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  仍有残留进程，建议手动检查${NC}"
    ps aux | grep -E "Auto-Claude|openclaw-gateway|Google Chrome" | grep -v grep
else
    echo -e "${GREEN}✅ 所有相关进程已清理${NC}"
fi

echo ""

echo -e "${BLUE}🚀 步骤 5/5: 重启建议${NC}"
echo ""

echo -e "${GREEN}✨ 系统已优化完成！${NC}"
echo ""
echo "📋 下一步操作："
echo ""
echo "1. 🔄 重新启动 Auto-Claude:"
echo "   open -a 'Auto-Claude'"
echo ""
echo "2. ⚙️  在Auto-Claude中应用性能设置:"
echo "   - 上下文窗口: 8000 tokens"
echo "   - 最大响应: 2000 tokens"
echo "   - 启用缓存: true"
echo "   - 历史压缩: true"
echo ""
echo "3. 📊 启动监控（可选）:"
echo "   bash scripts/monitor_auto_claude.sh"
echo ""
echo "4. 🎯 使用小任务策略:"
echo "   - 每个任务 < 1小时"
echo "   - 明确的验收标准"
echo "   - 独立可测试"
echo ""
echo -e "${YELLOW}💡 重要提示:${NC}"
echo "  - 定期重启 Auto-Claude (每6小时)"
echo "  - 监控任务进度，超过30分钟无进展应停止"
echo "  - 使用小任务而非大任务"
echo "  - 定期运行此优化脚本"
echo ""

# 询问是否立即重启Auto-Claude
read -p "是否立即重启 Auto-Claude？(y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在启动 Auto-Claude..."
    open -a "Auto-Claude"
    echo -e "${GREEN}✅ Auto-Claude 已启动${NC}"
    echo "等待应用完全加载（约30秒）..."
    sleep 30
    echo "✨ 现在可以开始使用了！"
else
    echo "请稍后手动启动 Auto-Claude"
fi

echo ""
echo -e "${GREEN}🎉 性能优化完成！${NC}"
echo ""
echo "📚 相关文档:"
echo "  - 详细指南: docs/AUTO_CLAUDE_PERFORMANCE_GUIDE.md"
echo "  - 立即行动: docs/IMMEDIATE_ACTION_PLAN.md"
echo "  - 配置文件: .autoflow/agent_performance_config.json"
