# HKMU Campus Platform — Codex Agent 指令

> 此文件由 `scripts/sync-ownership.sh` 从 `module-registry.json` 自动生成。
> 如需修改模块归属，请编辑 `module-registry.json` 后运行 `bash scripts/sync-ownership.sh`。

## 模块所有权注册表

| 模块 | 后端文件 | 前端文件 | 负责人 |
|------|----------|----------|--------|
| 学术规划 | `routers/courses.py` | `js/pages/academic.js` | [待分配] |
| 认证系统 | `routers/auth.py`, `services/auth_service.py` | `js/auth.js`, `js/pages/auth.js` | [待分配] |
| 社区论坛 | `routers/posts.py` | `js/pages/community.js` | [待分配] |
| 国际化 | — | `js/utils/i18n.js` | [待分配] |
| 失物招领 | `routers/lostfound.py` | `js/pages/lostfound.js` | [待分配] |
| 私信系统 | `routers/messages.py`, `services/websocket_manager.py` | `js/pages/messaging.js` | [待分配] |
| 校园新闻 | `routers/news.py` | `js/pages/news.js` | [待分配] |
| 用户管理 | `routers/users.py` | `js/pages/profile.js` | [待分配] |
| 共享基础 | `main.py`, `database.py`, `models.py`, `config.py` | `app.js`, `router.js`, `api.js`, `components/` | 所有人（改前通知） |

## 协作规则（必须遵守）

- **先拉后改**：每次开发前执行 `git pull origin main`
- **只改自己模块**：只修改自己负责的模块文件，不得修改他人模块
- **共享文件通知**：修改共享基础文件前必须在群内通知所有人
- **先读再改**：Agent 修改任何文件前必须先读取该文件完整内容
- **小步提交**：每完成一个功能点就 commit，不要积累大量改动
- **分支命名**：`feature/<模块名>-<功能描述>`
- **Commit 格式**：`[模块名] feat/fix/refactor: 描述`

## 技术栈

- 后端: FastAPI + SQLite (aiosqlite)
- 认证: JWT (python-jose) + bcrypt
- 前端: 原生 HTML/CSS/JS + Tailwind CDN
- 路由: Hash-based SPA
- 实时通信: WebSocket + REST 轮询降级

## 开发规范

- CSS 隔离：用 `data-page` 属性做页面级样式隔离
- UI 组件函数化：禁止散乱 DOM 拼接，所有可复用元素封装为函数
- XSS 防护：后端存储前 HTML 转义，前端用 textContent 不用 innerHTML
- API 前缀：`/api/v1/`
