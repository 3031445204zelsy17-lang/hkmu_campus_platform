#!/bin/bash
# check-file-ownership.sh
# Claude Code PreToolUse Hook: 检查 Agent 是否在修改他人负责的模块文件
#
# 数据源: module-registry.json（动态读取，新增模块自动生效）

FILE_PATH="$1"

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"
REGISTRY="$REPO_ROOT/module-registry.json"

if [ ! -f "$REGISTRY" ]; then
    exit 0
fi

# 检查 jq
if ! command -v jq &>/dev/null; then
    exit 0
fi

# 获取当前开发者
CURRENT_DEV=$(git -C "$REPO_ROOT" config user.name 2>/dev/null)
if [ -z "$CURRENT_DEV" ]; then
    exit 0
fi

# 标准化路径
normalize() {
    echo "$1" | sed 's|^\./||; s|^/||'
}
NORMALIZED_PATH=$(normalize "$FILE_PATH")

# 检查是否为共享文件
for shared_file in $(jq -r '.shared.backend[], .shared.frontend[]' "$REGISTRY" 2>/dev/null); do
    if [[ "$NORMALIZED_PATH" == *"$shared_file"* ]]; then
        echo "⚠️  共享文件: $FILE_PATH"
        echo "   修改前请确保已在群内通知所有团队成员。"
        exit 0
    fi
done

# 遍历所有模块，检查文件归属
for module in $(jq -r '.modules | keys[]' "$REGISTRY" 2>/dev/null); do
    owner=$(jq -r ".modules[\"$module\"].owner" "$REGISTRY")

    # 检查后端文件
    for mfile in $(jq -r ".modules[\"$module\"].backend[]?" "$REGISTRY" 2>/dev/null); do
        if [[ "$NORMALIZED_PATH" == *"$mfile"* ]]; then
            # 找到了归属模块
            if echo "$owner" | grep -q "待分配"; then
                exit 0  # 模块未分配，允许
            fi
            if echo "$owner" | grep -q "$CURRENT_DEV"; then
                exit 0  # 当前开发者是负责人，允许
            fi
            # 属于他人模块
            label=$(jq -r ".modules[\"$module\"].label" "$REGISTRY")
            echo "🚫 模块归属检查: $FILE_PATH"
            echo "   该文件属于 [$label] 模块，负责人: $owner"
            echo "   你 ($CURRENT_DEV) 不是该模块负责人。"
            echo "   如需修改，请先联系 $owner 确认。"
            exit 1
        fi
    done

    # 检查前端文件
    for mfile in $(jq -r ".modules[\"$module\"].frontend[]?" "$REGISTRY" 2>/dev/null); do
        if [[ "$NORMALIZED_PATH" == *"$mfile"* ]]; then
            if echo "$owner" | grep -q "待分配"; then
                exit 0
            fi
            if echo "$owner" | grep -q "$CURRENT_DEV"; then
                exit 0
            fi
            label=$(jq -r ".modules[\"$module\"].label" "$REGISTRY")
            echo "🚫 模块归属检查: $FILE_PATH"
            echo "   该文件属于 [$label] 模块，负责人: $owner"
            echo "   你 ($CURRENT_DEV) 不是该模块负责人。"
            echo "   如需修改，请先联系 $owner 确认。"
            exit 1
        fi
    done
done

# 文件不属于任何已注册模块（新文件等），允许修改
exit 0
