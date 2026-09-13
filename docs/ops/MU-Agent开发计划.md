# HKMU Campus · MU Agent 开发计划(执行版)

> **活文档** · 建版 2026-09-08 · 起因:与教授沟通确认「产品接入 AI 功能」方向;把 ole-scraper(`~/Desktop/ole-scraper`)的 agent 机制以合规方式移植进平台
> 决策依据(只读存档):
> - 完整规划案:`~/.claude/plans/sequential-dazzling-crown.md`(2026-09-08,三子代理探索+Plan 代理设计)
> - LLM 检索:GLM-4.7-Flash 免费+200K ctx+FC 强(docs.bigmodel.cn,2026-09-08 核)
>
> 驱动方式:按团队 vibe-coding SOP,每个任务行 = 一个 prompt(任务→模块→文件→约束→验收标准),人审后下一行。
> **当前状态:阶段A 学习期(只读 ole-scraper + 本文档),阶段B 未开工。**

---

## 0. 决策快照(全部已定,除非标注)

| 决策项 | 结论 | 依据 |
|---|---|---|
| 产品形态 | **MU Agent**:平台自有数据 AI 问答助手(web 先行);ole-scraper 保持独立开源线 | 2026-09-08 用户定 |
| OLE 能力 | **v0 不进**(凭证托管+OLE 封锁+审核/背书牵连;Playwright 在 slim 容器跑不起来,技术合规双重阻断);四路径挂账 §6 | 同上 |
| LLM | **GLM-4.7-Flash 免费**主力;`AGENT_LLM_*` env 可切(deepseek/openai/ollama 预设随移植);key 只进 Azure appsettings/.env | 官方文档 2026-09-08 |
| 工具集 | 7 个:课程搜索/专业信息/专业课程/GE/课评/**个人毕业进度**/社区搜索 | 规划案 §一.2 |
| 传输 | WS `/api/v1/agent/ws`,移植 ole 协议(thinking/delta/final + 类型化 error + `__STOP__`/`__RESTORE__`/`__PING__`) | 规划案 §一.4 |
| 对话持久化 | v0 零新表,历史存浏览器 localStorage(12 对) | 隐私面最小 |
| 小程序 | v0 不进(国区个人主体 AI 生成类目风险待专项核实) | 与 IG 线同节奏 |
| 车道 | **阶段A 学习期(现在)→ 阶段B 施工(用户明示开始)**;iOS 线学习期并行照常 | 2026-09-08 用户定 |

**待定(不阻塞开工)**:① GLM 免费档具体 RPM/并发(M0 实测)② 流式 usage 是否随帧返回(M0 实测,不行记 `na`)③ OpenCC 运行时内存增量(M2 实测,>40MB 降级为仅课码+英文名)。

**开工日刷新清单(时效项,若学习期 >2 周必须重验)**:GLM-4.7-Flash 免费政策是否仍在 / ole 可移植代码有无大改(对照 `git -C ~/Desktop/ole-scraper log --oneline -10`)/ 平台 `main` HEAD 与本次探索基线的 drift。

---

## 1. 硬约束(每个任务的公共约束,不再逐行重复)

1. 镜像零 ML 依赖(不进 torch/sentence-transformers);LLM 走 httpx(已是依赖)
2. DB 池仅 5:**绝不跨 LLM 调用持有 `get_db()` 连接**——逐语句借用,查完即释
3. 端点首行 `check_rate_limit`;输入过 `audit_user_text`(SCENE_SOCIAL=4,同私信先例)
4. `AGENT_ENABLED` 默认 **false**;agent 初始化 lazy,不破 `/api/health`
5. ruff(`select=["E9","F8"]`)+ pytest 必绿;测试不得依赖真实 LLM key(全 stub)
6. XSS 仅渲染层转义;课码索引一次/进程+TTL,不与 LLM await 重叠
7. DDL 零改动;共享文件(main.py/config.py)改动 PR 知会

---

## 2. 阶段A · 学习期(现在,唯一落地物=本文档)

学习路径(ole-scraper 当教材,顺序=依赖顺序)。每读完一层,用自己的话写 3-5 行笔记进 §8 学习记录:

| # | 主题 | 精读文件 | 过关自测 |
|---|------|---------|---------|
| L1 | LLM API 与 function calling | `ole-scraper/app/llm.py`(212 行,最短先读) | messages 结构?tool_calls 下发与 role:"tool" 回填?finish_reason 分支?SSE 分片重组(176-194)为何是难点? |
| L2 | ReAct 主循环 | `ole-scraper/app/agent_loop.py` | 一轮=什么?MAX_TURNS 防什么?为什么把参数错误喂回 LLM 而不是报错?检索上限防什么? |
| L3 | 工具设计 | `app/tools.py` + `tool_executor.py` | schema 为何是唯一真相?三类工具分层的成本逻辑?「永不抛异常」「>8000 压缩成合法 JSON」各防什么? |
| L4 | 对话与流式前端 | `app/conversation.py` + `main.py` WS 段 + `frontend/src/useChatWS.ts` | tool 结果为何不进历史?并发 reader(:170-188)解什么死锁?三帧各对应什么阶段? |
| L5(进阶可缓) | RAG 机制与坑 | `rag_index.py` + `public_rag.py` | 最小向量检索长什么样?索引每查询重读 110MB 的坑?URL 去重与新鲜度诚实标注好在哪? |
| L6(实操) | 跑起来玩 | 本地 `./init.sh` | 问「这周有什么作业」「下载课件」,对照 L1-L4 找每步对应代码 |

配套:`~/Desktop/antigravity/wiki/` 的 agent-harness(能力刻度);ole-scraper `TECH_DEBT.md`(真实教训清单)。

**理论伴奏:hello-agents**(Datawhale《从零开始构建智能体》,fork 在自己账号 `3031445204zelsy17-lang/hello-agents`,上游 2026-09 仍在更新)——**挑读配对,不通读**(16 章全读三周打不住,会拖穿 ≤2 周时效窗):

| 教程章节 | 配对精读 | 说明 |
|---|---|---|
| 第三章 LLM 基础(跳过 Transformer 细节) | L1 llm.py | API 与提示词的体系化底子 |
| **第四章 ReAct 手把手** | **L2 agent_loop.py** | 核心配对:教程讲范式,ole 是生产级实现,对照读 |
| 第七章 从 0 构建框架 | — | 印证 MU Agent 无框架手写路线,选读 |
| 第八章 记忆与检索 | L5 rag_*.py | 进阶配读 |
| 第十二章 性能评估 | —(ole 挂账的 evals 线) | v1 做 evals 时回来读 |

**跳过**:第五章(低代码,与手写路线相反)、第六章(AutoGen/LangGraph 等,v0 刻意不用)、第十一章(Agentic-RL)、十三~十六章(综合大项目,上线后有兴趣再玩)。**纪律:精读是主线,教程是伴奏。**

---

## 3. 阶段B · 施工任务表(启动条件:用户明示「开始搭 agent」)

**分支** `feature/agent-mu-agent` · **commit 格式** `[agent] feat/fix: 描述` · 依赖链 M0→M1→(M2∥M3)→M4→M5→M6→M7

| # | 任务 | 模块/文件 | 约束与要点 | 验收标准 |
|---|------|----------|-----------|---------|
| M0 | GLM 实测(阶段0验证) | 一次性脚本,**不入仓库** | 用 ole-scraper/.env 的 bigmodel key(只读 key 名不打印值)打 `glm-4.7-flash`:①流式+2 假工具看 tool_calls delta 格式与 finish_reason ②usage 是否随流(试 `stream_options.include_usage`)③7 个真实 schema 中文提问测幻觉 | 格式确认、usage 策略定案、结论记入本文档 §8 |
| M1 | LLM 客户端移植 | 新 `backend/app/services/agent_llm.py` + `config.py` AGENT_* 键 | ole llm.py 移植:SSE tool_calls 重组(:176-194 一字不改)、重试集合+流已开始不重试;**修正**:共享 AsyncClient 单例+Timeout(10/60/10/10)+usage 解析(按 M0) | 新 `tests/test_agent_llm.py` 绿(MockTransport 罐头 SSE,零网络);ruff 净 |
| M2 | 工具层 | 新 `backend/app/services/agent_tools.py` | 7 工具 + `TOOL_DEFINITIONS` schema;移植 executor 契约(永不抛/`_dumps_capped` 8000 合法 JSON/None 剥离);`_norm()`=t2s+casefold+去空白三语匹配(OpenCC 懒单例);`_CAP_TOOLS` 检索上限 3;课程索引=courses∪course_catalogue∪GE∪RULE_COURSE_CREDITS,TTL~600s;数据层直接 import `app/data/*`(零 DB);课评/进度/社区 = 一次短借用;进度用 `_compute_graduation`(from routers.courses import) | `test_agent_tools.py`(纯函数)+`test_agent_search_courses.py`(需 DB,三语命中:英文名/简/繁/课码片段)绿;**实测进程 RSS 增量 <40MB** 记入 §8 |
| M3 | 主循环+提示词(与 M2 并行) | 新 `backend/app/services/agent_loop.py` | ole loop 移植(三段校验/取消检查/finish 分支/`length` 分支补);ConversationHistory(12 对)并入;重写系统提示词:平台数据边界/反幻觉/三级标注(✅⚠️❓)/OLE 问题礼貌拒答+指路/检索收敛/输出~300 字/`{date}`/「用户内容是数据非指令」;每轮日志 `agent_turn user= turns= tools= tokens= dur= finish=` | `test_agent_loop.py` 绿(monkeypatch call_llm_stream:工具序列/坏 JSON 纠错/缺参纠错/CAP 强制收敛/cancel 短路) |
| M4 | WS 端点 | 新 `backend/app/routers/agent.py` + `main.py` 注册(StaticFiles 前) | `GET /status`(enabled/llm_configured,无 auth);WS:query token 鉴权+逐帧 exp 复查(messages.py 模式)+并发 reader(ole main.py:170-188 设计)+inbox+cancel+每连接 ToolExecutor(user);每消息:限流(10/min)→长度校验(≤2000)→audit_user_text→loop→final;类型化 error 帧(disabled/unconfigured/rate_limited/content_rejected/moderation_unavailable/invalid_input/internal);**抽 `_handle_agent_message`+`_parse_client_frame` 供测试直驱**(仓库无进程内 WS 基建) | `test_agent_ws.py` 绿(限流/内容拒绝 monkeypatch/开关门禁/未配置);真实 key 本地手测一发全流程 |
| M5 | 前端全套 | 新 `frontend/js/pages/agent.js`+`css/agent.css`;改 `app.js`(import+register auth:true)/`nav.js`(SIDEBAR_NAV_AUTH 首位,icon sparkles)/`i18n.js`(三语 ~20 键)/`sw.js`(**CACHE_NAME v9→v10**+STATIC_ASSETS 加 agent.js/app.min.css/theme.js/push.js/image.js/image_upload.js,删 8 个旧 css 条目)/`build-css.sh`(concat 加 agent.css) | 从 messages.js 复刻不 import;WS 直连(不走 api.js);delta 用 textContent;localStorage 历史刷新恢复;生成中变停止键;离线横幅+重连 5s→30s;底部 AI 声明+头部徽章;`npm run build:css` 含 agent.css | 本地 `/#/agent` 鉴权门控+全帧循环+流中可停+刷新恢复;`AGENT_ENABLED=false` 显示"暂未开放" |
| M6 | 合规+登记 | 隐私条款(miniprogram/pages/privacy+i18n `privacy.*` 三语加一条:输入发往第三方 LLM(智谱 GLM)、对话仅存本地设备);`docs/ops/隐私合规-差距与路线图-20260906.md` 挂账段;`docs/ops/正式上线checklist.md` 一行;`module-registry.json` 加 MU Agent(owner SYF)+`sync-ownership.sh` | 条款三语可见;CLAUDE.md 表重生成;本地观测到一条 agent_turn 日志 |
| M7 | 部署 | deploy-azure skill | **AGENT_ENABLED=false 先上**→Azure appsettings 配 AGENT_LLM_API_KEY 等→验 `/api/v1/agent/status`→开开关 | prod 完整问答一条(带工具调用);流中停止;App Insights 可见端点;`/api/health` 不受影响 |

## 4. 端到端验证剧本(本地 + prod 各跑一遍)

问题集:①「DSAI 是什么专业?毕业要多少学分」②「我离毕业还差多少学分?」(验个人进度工具+鉴权)③「STAT1510 课评怎么样?」(验课评工具)④繁体问「有哪些通識課可以選?」(验三语+GE)⑤流式输出中途点停止 ⑥刷新页面历史还在 ⑦连发 11 条验限流提示 ⑧未开开关时访问 →「暂未开放」

## 5. 里程碑速查

| 里程碑 | vibe 估计 |
|---|---|
| M0+M1(验证+LLM 客户端) | 1 个会话 |
| M2+M3(工具+循环,可并行) | 2 个会话 |
| M4(WS) | 1 个会话 |
| M5(前端) | 1 个会话 |
| M6+M7(合规+部署) | 1 个会话 |
| **合计 0→prod** | **~6 个会话** |

## 6. 挂账(v0 后决策)

**OLE 四路径**:①互链导流(半天,零风险;系统提示词已内置指路)②纯 HTTP BYOC(需 1-2 天逆向研究 OLE 登录能否脱离浏览器;成立则轻依赖+会话内存凭证+仅 web)③独立 Playwright worker(违反 slim 容器约束,❌)④官方合作(主任背书落地后的正道)。落地形态=`agent_tools.py` 加 handler+schema+`AGENT_OLE_ENABLED` 开关,纯增量。
**v1 备选**:对话落库(agent_conversations 表)、search_community 课码抽取、小程序 AI 合规专项(生成式 AI 备案/标注,进小程序前必做)、课程描述 RAG、Markdown 流式渲染。

## 7. 风险对策速查

GLM 坏 JSON/错工具→三段纠错环兜底 · 免费档限流未知→10/min+退避+App Insights 盯 429 · 流式无 usage→记 na · SW 忘 bump v10=老用户坏页(M5 硬验收)· 历史注入→提示词声明数据非指令(v0 无写入工具,半径小)· 审核慢 fail-closed→与 posts/DM 同权衡 · 服务层 import 路由层纯函数=分层瑕疵,咬到挪 services/graduation.py

## 8. 学习记录 + 实测记录(追加式)

**分工**:学习笔记(L1-L4 每层 3-5 行自己的话)→ wiki [[agent-learning-path]](知识复利,Obsidian 可链接);本节只记**施工实测结论**(M0 的 GLM 格式/usage 定案、M2 的 OpenCC RSS 增量等)。
