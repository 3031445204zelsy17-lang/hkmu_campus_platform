# HKMU Campus Platform

整合 HKMU Campus Forum + MUwall 的全栈校园综合平台。

## 技术栈

| 层面 | 技术 |
|------|------|
| 后端 | FastAPI + SQLite (aiosqlite) |
| 认证 | JWT (python-jose) + bcrypt (passlib) |
| 前端 | 原生 HTML/CSS/JS + Tailwind CDN |
| 路由 | Hash-based SPA |
| 实时通信 | WebSocket + REST 轮询降级 |
| 移动端 | PWA (manifest + Service Worker) |
| 国际化 | data-i18n 系统（三语言） |

## 项目结构

```
hkmu-campus-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 环境配置
│   │   ├── database.py          # SQLite 连接 + 建表
│   │   ├── models.py            # Pydantic 模型
│   │   ├── routers/             # API 路由
│   │   │   ├── auth.py
│   │   │   ├── posts.py
│   │   │   ├── courses.py
│   │   │   ├── users.py
│   │   │   ├── messages.py
│   │   │   ├── news.py
│   │   │   └── lostfound.py
│   │   └── services/
│   │       ├── auth_service.py
│   │       ├── sanitizer.py
│   │       └── websocket_manager.py
│   ├── .env
│   └── requirements.txt
├── frontend/
│   ├── index.html               # SPA 壳
│   ├── css/
│   ├── js/
│   │   ├── app.js
│   │   ├── router.js
│   │   ├── api.js
│   │   ├── auth.js
│   │   ├── components/
│   │   ├── pages/
│   │   └── utils/
│   └── assets/
└── scripts/
    ├── seed_courses.py
    └── dev.py
```

## 启动命令

```bash
# 开发服务器（必须用 python -m，避免环境不一致）
cd /Users/yifanshi/Desktop/hkmu-campus-platform
python -m uvicorn backend.app.main:app --reload --port 8000

# 或使用 dev 脚本
python scripts/dev.py

# Swagger UI
# http://localhost:8000/docs
```

## 开发规范

- CSS 隔离：用 `data-page` 属性做页面级样式隔离
- UI 组件函数化：禁止散乱 DOM 拼接，所有可复用元素封装为函数
- XSS 防护：后端存储前 HTML 转义，前端用 textContent 不用 innerHTML
- API 前缀：`/api/v1/`
- Git 提交格式：`feat: T0X - 描述` / `progress: T0X done`

## 验证规则

| 任务类型 | 验证方式 |
|---------|---------|
| 后端新增文件 | `python -m py_compile backend/app/xxx.py` |
| API 端点 | 服务启动后 `curl http://localhost:8000/api/health` |
| 数据库 | 确认 campus.db 表已创建 |
| 前端页面 | 浏览器访问确认渲染 |

## 来源项目

| 项目 | 路径 | 复用内容 |
|------|------|---------|
| HKMU Campus Forum | `/Users/yifanshi/Desktop/HKMU_Campus_Forum/` | 43门课程数据、用户系统、蓝绿视觉风格 |
| MUwall | (GitHub) | 社区信息流、毛玻璃CSS、i18n、SPA路由 |

## 团队协作规范 (Team Collaboration)

> 此部分由 `scripts/sync-ownership.sh` 从 `module-registry.json` 自动生成。
> 如需修改模块归属，请编辑 `module-registry.json` 后运行 `bash scripts/sync-ownership.sh`。

### 模块所有权注册表

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

### 协作规则

- **先拉后改**：每次开发前执行 `git pull origin main`
- **只改自己模块**：只修改自己负责的模块文件，不得修改他人模块
- **共享文件通知**：修改共享基础文件前必须在群内通知所有人
- **先读再改**：Agent 修改任何文件前必须先读取该文件完整内容
- **小步提交**：每完成一个功能点就 commit，不要积累大量改动
- **分支命名**：`feature/<模块名>-<功能描述>`
- **Commit 格式**：`[模块名] feat/fix/refactor: 描述`

## 详细计划

完整实施计划见：`/Users/yifanshi/Desktop/校园论坛计划/HKMU_Campus_Platform_优化计划.md`
