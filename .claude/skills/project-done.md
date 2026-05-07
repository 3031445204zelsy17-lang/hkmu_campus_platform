# Project Done — 任务完成提交

每完成一个 `progress.json` 中的任务后使用。

## 执行步骤

### 1. 确认任务

回顾当前任务：
- 对应 `progress.json` 中的哪个 ID
- 该任务的 description 是什么
- 实际完成内容是否与描述一致

### 2. 运行验证

根据项目类型和任务阶段执行对应验证。

**通用验证（每次都做）：**
```bash
# 确认没有语法错误
# Python 项目
python -c "from app.xxx import yyy; print('OK')"
# 或直接运行检查
python -m py_compile <修改的文件>

# 确认服务能启动（如有 API）
curl http://localhost:8000/api/health

# 看改动范围
git diff --stat
```

**按任务类型追加验证：**

> 如果项目 CLAUDE.md 中定义了「验证规则」，按规则执行。
> 以下为通用参考：

| 任务类型 | 验证方式 |
|---------|---------|
| 新增 API 端点 | curl 测试 + 检查返回格式 |
| 新增页面/组件 | 打开浏览器确认渲染 |
| 数据处理 | 检查输出文件存在且非空 |
| 数据库操作 | 确认表已创建、CRUD 正常 |
| 配置/基础设施 | 确认服务能启动 |
| 测试 | 运行测试套件，确认通过 |

### 3. 查看改动范围

```bash
git diff --stat
git status --short
```

确认只改了**这个任务相关**的文件。如果动了不相关的文件，提醒用户决定是否保留。

### 4. 提交代码

```bash
# 添加具体文件（不用 add -A）
git add <具体文件列表>

# 提交，格式: 类型: 任务ID - 描述
git commit -m "feat: T0X - 功能描述"
# 或
git commit -m "fix: T0X - 修复描述"
```

### 5. 更新进度文件

编辑 `progress.json`，将对应任务的 `passes` 改为 `true`。

**只修改本次完成的任务，不要动其他条目。**

```bash
git add progress.json
git commit -m "progress: T0X done"
```

### 6. 输出完成报告

```
T0X 完成
━━━━━━━━━━━━━━━━━━━━━━━━
任务: [任务名称]
改动/生成文件:
  - [列出修改或新建的文件]

验证结果:
  - [验证检查的结果摘要]

进度: X/N 完成 (Phase/K 名称)

下一个任务: [ID] - [描述]
下次对话输入 /project-start 继续
```

### 7. 阶段完成通知（如适用）

当某个 phase 的所有任务都 passes: true 时，额外输出：

```
Phase/K 全部完成!
本阶段产出:
  - [列出关键文件和数据]

准备进入下一阶段: [阶段名称]
下次对话输入 /project-start 继续
```

---

## 异常处理

| 情况 | 处理 |
|------|------|
| 验证失败 | 不标记 passes: true，输出错误信息让用户决定 |
| 前置依赖未完成 | 提醒用户，建议先完成前置任务 |
| 改动了不相关文件 | 提醒用户，让用户决定是否拆分提交 |
| progress.json 格式损坏 | 提示修复，不要强行写入 |

---

## Git 提交格式

```
feat: T0X - 新增功能描述
fix: T0X - 修复问题描述
refactor: T0X - 重构描述
style: T0X - 样式调整描述
docs: T0X - 文档更新描述
progress: T0X done  ← 更新 progress.json 专用
```
