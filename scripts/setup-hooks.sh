#!/bin/bash
#
# setup-hooks.sh — 一键安装 Git hooks
# 使用方法: bash scripts/setup-hooks.sh
#

REPO_ROOT="$(git rev-parse --show-toplevel)"

if [ ! -d "$REPO_ROOT/.githooks" ]; then
    echo "❌ 未找到 .githooks 目录"
    exit 1
fi

# 复制 pre-commit hook
cp "$REPO_ROOT/.githooks/pre-commit" "$REPO_ROOT/.git/hooks/pre-commit"
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"

# 设置 Git 使用项目 hooks 目录（备选方案）
git config core.hooksPath .githooks

echo "✅ Git hooks 安装完成"
echo "   - pre-commit: 文件归属检查已启用"
echo ""
echo "   团队成员 clone 项目后，请运行："
echo "   bash scripts/setup-hooks.sh"
