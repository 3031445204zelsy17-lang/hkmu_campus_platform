# Project Review — 项目验收

所有任务完成后使用。全量测试 + 人工审查 + 最终收尾。

## 执行步骤

### 1. 确认全部完成

读取 `progress.json`，确认所有任务 `passes: true`。

如果有未完成的，列出并回到执行阶段。

### 2. 全量测试

根据项目类型运行完整测试：

**通用检查：**
```bash
# 确认 git 工作区干净
git status --short

# 看完整提交历史
git log --oneline

# 检查项目结构完整性
find . -type f -not -path './.git/*' -not -path './.claude/*' | sort
```

**按项目类型追加：**

| 项目类型 | 验证方式 |
|---------|---------|
| Web 应用 | 启动服务，逐个功能手动测试 |
| 数据分析 | 从头运行完整 pipeline，确认无报错 |
| CLI 工具 | 运行所有命令组合 |
| 库/包 | 运行完整测试套件 |

### 3. 代码审查

```bash
# 看总改动量
git diff --stat <initial-commit>..HEAD

# 看是否有遗留的调试代码
grep -rn "console.log\|print('DEBUG\|breakpoint\|TODO\|FIXME\|HACK" --include="*.py" --include="*.js" --include="*.ts" .
```

检查项：
- [ ] 没有遗留的调试代码（console.log / print / breakpoint）
- [ ] 没有硬编码的密钥或密码
- [ ] 没有 TODO/FIXME 未处理（或已记录为后续任务）
- [ ] .gitignore 排除了敏感文件（.env、*.db 等）
- [ ] README.md 反映了最终项目状态

### 4. 清理

```bash
# 删除空文件和临时文件
find . -name "*.tmp" -o -name "*.bak" -o -name ".DS_Store" | xargs rm -f 2>/dev/null

# 如果有改动，提交
git add -A
git commit -m "chore: final cleanup"
```

### 5. 输出验收报告

```
项目验收报告
━━━━━━━━━━━━━━━━━━━━━━━━
项目: [项目名称]
总任务: N 个，全部完成
总提交: X 个

产出清单:
  [列出所有关键文件和目录]

功能测试:
  ✅ [测试1]
  ✅ [测试2]
  ...

代码质量:
  [审查结果摘要]

下一步建议:
  - [如需部署、写文档、发布等]
```

### 6. 更新项目记忆

如果有项目记忆系统（如 CLAUDE.md 或 memory/），更新：
- 项目状态改为「已完成」
- 记录关键决策和最终架构
- 记录已知限制和后续改进方向
