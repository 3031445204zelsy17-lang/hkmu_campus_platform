#!/bin/bash
#
# sync-ownership.sh — 从 module-registry.json 同步所有协作配置
# 使用方法: bash scripts/sync-ownership.sh
#
# 新增模块只需:
#   1. 编辑 module-registry.json
#   2. 运行 bash scripts/sync-ownership.sh
#

set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
REGISTRY="$REPO_ROOT/module-registry.json"

if [ ! -f "$REGISTRY" ]; then
    echo "❌ 未找到 module-registry.json"
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo "❌ 需要 jq。安装: brew install jq"
    exit 1
fi

echo "📋 同步协作配置..."

# ============================================
# 生成 Markdown 表格
# ============================================
TMP_TABLE=$(mktemp)
{
    echo "| 模块 | 后端文件 | 前端文件 | 负责人 |"
    echo "|------|----------|----------|--------|"

    for module in $(jq -r '.modules | keys[]' "$REGISTRY"); do
        label=$(jq -r ".modules[\"$module\"].label" "$REGISTRY")
        owner=$(jq -r ".modules[\"$module\"].owner" "$REGISTRY")

        backend_raw=$(jq -r ".modules[\"$module\"].backend[]? // empty" "$REGISTRY" | tr '\n' ',' | sed 's/,$//')
        frontend_raw=$(jq -r ".modules[\"$module\"].frontend[]? // empty" "$REGISTRY" | tr '\n' ',' | sed 's/,$//')

        if [ -n "$backend_raw" ]; then
            backend_str=$(echo "$backend_raw" | sed 's/,/`, `/g' | sed 's/^/`/;s/$/`/')
        else
            backend_str="—"
        fi

        if [ -n "$frontend_raw" ]; then
            frontend_str=$(echo "$frontend_raw" | sed 's/,/`, `/g' | sed 's/^/`/;s/$/`/')
        else
            frontend_str="—"
        fi

        echo "| $label | $backend_str | $frontend_str | $owner |"
    done

    shared_be=$(jq -r '.shared.backend[]' "$REGISTRY" | tr '\n' ',' | sed 's/,$//' | sed 's/,/`, `/g' | sed 's/^/`/;s/$/`/')
    shared_fe=$(jq -r '.shared.frontend[]' "$REGISTRY" | tr '\n' ',' | sed 's/,$//' | sed 's/,/`, `/g' | sed 's/^/`/;s/$/`/')
    echo "| 共享基础 | $shared_be | $shared_fe | 所有人（改前通知） |"
} > "$TMP_TABLE"

# ============================================
# 生成规则列表
# ============================================
TMP_RULES=$(mktemp)
jq -r '.rules | to_entries[] | "- **\(.key)**：\(.value)"' "$REGISTRY" > "$TMP_RULES"

# ============================================
# 更新 AGENTS.md（全量重写）
# ============================================
{
    echo "# HKMU Campus Platform — Codex Agent 指令"
    echo ""
    echo "> 此文件由 \`scripts/sync-ownership.sh\` 从 \`module-registry.json\` 自动生成。"
    echo "> 如需修改模块归属，请编辑 \`module-registry.json\` 后运行 \`bash scripts/sync-ownership.sh\`。"
    echo ""
    echo "## 模块所有权注册表"
    echo ""
    cat "$TMP_TABLE"
    echo ""
    echo "## 协作规则（必须遵守）"
    echo ""
    cat "$TMP_RULES"
    echo ""
    echo "## 技术栈"
    echo ""
    echo "- 后端: FastAPI + SQLite (aiosqlite)"
    echo "- 认证: JWT (python-jose) + bcrypt"
    echo "- 前端: 原生 HTML/CSS/JS + Tailwind CDN"
    echo "- 路由: Hash-based SPA"
    echo "- 实时通信: WebSocket + REST 轮询降级"
    echo ""
    echo "## 开发规范"
    echo ""
    echo "- CSS 隔离：用 \`data-page\` 属性做页面级样式隔离"
    echo "- UI 组件函数化：禁止散乱 DOM 拼接，所有可复用元素封装为函数"
    echo "- XSS 防护：后端存储前 HTML 转义，前端用 textContent 不用 innerHTML"
    echo "- API 前缀：\`/api/v1/\`"
} > "$REPO_ROOT/AGENTS.md"
echo "✅ AGENTS.md"

# ============================================
# 更新 CLAUDE.md（替换协作规范部分）
# ============================================
CLAUDE_MD="$REPO_ROOT/CLAUDE.md"
if [ -f "$CLAUDE_MD" ]; then
    # 生成新的协作部分
    TMP_COLLAB=$(mktemp)
    {
        echo "## 团队协作规范 (Team Collaboration)"
        echo ""
        echo "> 此部分由 \`scripts/sync-ownership.sh\` 从 \`module-registry.json\` 自动生成。"
        echo "> 如需修改模块归属，请编辑 \`module-registry.json\` 后运行 \`bash scripts/sync-ownership.sh\`。"
        echo ""
        echo "### 模块所有权注册表"
        echo ""
        cat "$TMP_TABLE"
        echo ""
        echo "### 协作规则"
        echo ""
        cat "$TMP_RULES"
    } > "$TMP_COLLAB"

    if grep -q "## 团队协作规范" "$CLAUDE_MD"; then
        # 替换协作规范 → 详细计划之间的内容
        TMP_RESULT=$(mktemp)
        awk '
        /^## 团队协作规范/ { skip=1; while ((getline line < "'"$TMP_COLLAB"'") > 0) print line; next }
        /^## 详细计划/ { skip=0 }
        !skip { print }
        ' "$CLAUDE_MD" > "$TMP_RESULT"
        mv "$TMP_RESULT" "$CLAUDE_MD"
    else
        # 追加到末尾
        echo "" >> "$CLAUDE_MD"
        cat "$TMP_COLLAB" >> "$CLAUDE_MD"
    fi
    rm -f "$TMP_COLLAB"
    echo "✅ CLAUDE.md"
fi

# ============================================
# 更新 CODEOWNERS
# ============================================
mkdir -p "$REPO_ROOT/.github"
{
    echo "# HKMU Campus Platform — 模块所有权"
    echo "# 由 scripts/sync-ownership.sh 从 module-registry.json 自动生成"
    echo ""

    for module in $(jq -r '.modules | keys[]' "$REGISTRY"); do
        label=$(jq -r ".modules[\"$module\"].label" "$REGISTRY")
        github=$(jq -r ".modules[\"$module\"].github" "$REGISTRY")
        tag="@${github}"

        echo "# $label"
        for file in $(jq -r ".modules[\"$module\"].backend[]? // empty" "$REGISTRY"); do
            echo "/backend/app/$file $tag"
        done
        for file in $(jq -r ".modules[\"$module\"].frontend[]? // empty" "$REGISTRY"); do
            echo "/frontend/$file $tag"
        done
        echo ""
    done

    echo "# 共享基础 — 需要全员 review"
    all_tags=$(jq -r '[.members[].github | "@" + .] | join(" ")' "$REGISTRY")
    for file in $(jq -r '.shared.backend[]' "$REGISTRY"); do
        echo "/backend/app/$file $all_tags"
    done
    for file in $(jq -r '.shared.frontend[]' "$REGISTRY"); do
        echo "/frontend/$file $all_tags"
    done
    echo ""
    echo "# 默认"
    echo "* $all_tags"
} > "$REPO_ROOT/.github/CODEOWNERS"
echo "✅ .github/CODEOWNERS"

# ============================================
# 清理
# ============================================
rm -f "$TMP_TABLE" "$TMP_RULES"

echo ""
echo "🎉 同步完成！"
echo ""
echo "工作流："
echo "  1. 编辑 module-registry.json（新增模块或修改归属）"
echo "  2. 运行 bash scripts/sync-ownership.sh"
echo "  3. 所有配置自动同步到 CLAUDE.md / AGENTS.md / CODEOWNERS"
