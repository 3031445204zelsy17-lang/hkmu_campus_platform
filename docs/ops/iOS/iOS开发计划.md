# HKMU Campus · iOS 开发计划(执行版)

> **活文档** · 建版 2026-09-07 · 栈/路线/登录/审核选型已全部定案,本文档是唯一执行入口
> 决策依据(只读存档,不再更新):
> - `docs/ops/iOS/iOS端技术栈评估.md`(2026-07-31,四栈对比,同目录)
> - `docs/ops/iOS/iOS上架路线对比-外区vs国区-20260907.md`(路线/标准/红档核实/周期,同目录)
>
> 驱动方式:按团队 vibe-coding SOP,每个任务行 = 一个 prompt(任务→模块→文件→约束→验收标准),人审后下一行。

---

## 0. 决策快照(全部已定,除非标注)

| 决策项 | 结论 | 依据 |
|---|---|---|
| 技术栈 | **RN + Expo**(EAS 云构建免 Mac) | 7-31 评估 |
| 路线 | **A TestFlight → B 外区正式**(同一套产物);C 国区挂起阶段 2 | 9-07 对比 §3-4 |
| 登录 | **邮箱(带验证,已有)+ Google + Apple 三件套**;社交登录邮箱视为已验证;须加单 OAuth 槽防覆盖守卫 | 9-07 用户定 + §9.2 |
| 内容审核 | **L1 词库+OpenCC → L2 双活(OpenAI 免费 + 阿里国际站 SG)fail-closed**;微信用户继续 imgSecCheck | 9-07 arch-check §9.3 |
| 校名 5.2.1 | **首审按去官方化准备**:中性名候选 ×2-3 + 描述声明学生独立开发 + 去校徽素材;主任背书信到手后作加强证据 | §9.4 |
| 图片上传 | 照抄现有 `/upload` 代理链,**后端零改** | §9.1 |
| 推送 | expo-notifications + APNs(唯一原生面) | — |
| 私信 | 先轮询(复用 web 方案),真 WS 后续试 | — |

**待定(不阻塞开工)**:① L2 主备顺序(30 条三语样本自评后定,或直接拍)② 阶段 0 假设验证跑不跑(1 周零成本,建议跑)。

**开工日刷新清单(半天,时效项)**:✅ 2026-09-11 已核(SDK 57 / EAS 15 次 iOS 构建每月、模拟器构建不需 Apple 号 / Xcode 26.6 镜像已有 / OpenAI moderation 免费但账号须绑卡 / Apple 国区 ¥688、区域与上架解耦)——详见 `docs/ops/iOS/iOS开工前置清单.md` §四。

---

## 1. 阶段一:后端前置合规(不依赖 iOS 决策,现存风险修复)

**分支** `feature/ios-backend-compliance` · **工期** vibe 2-3 天(B9 占增量;2026-09-11 双工具复核后上调)· **CI** pytest 门禁全绿(本地跑法见 memory:brew postgres env 覆盖)

> **2026-09-11 双工具复核**(Codex 17 findings → CC 对码逐条验):可见 11 条中 7 条成立采纳、2 条半成立(方向对事实有偏)、1 条对现状不成立(prod 开关 az 实查为 true)。修订已并入下表;**缺页 6 条(原文 #3/4/9/10/14/15)待补粘后续验**。

| # | 任务 | 模块/文件 | 约束 | 验收标准 |
|---|---|---|---|---|
| B1 | L1 本地审核引擎 | 新 `backend/app/services/moderation_local.py`;词表 `backend/app/resources/sensitive_words*.txt`(konsheng MIT 裁剪版,不入全量 GFW 表) | OpenCC t2s 归一 → Aho-Corasick/trie 匹配;进程内零网络;启动加载一次;命中返回类别 | 单测:繁体变体命中简体词表;正常校园帖零误杀样本通过 |
| B2 | L2 远程审核双活 | 新 `backend/app/services/moderation_remote.py` | OpenAI moderation + 阿里国际站 SG 两 client;**结果格(9-11 复核定)**:≥1 个有效 pass **且 0 个 block/review** 才放行;pass+provider 超时→放行;block/review+超时→拦截;全部不可用(含未配置)→503 fail-closed;超时 10s(沿用 stable_token 教训);key 走 env,无 key 的 provider 记 unavailable 不炸 | mock 单测覆盖**六路**:正常放行/命中拦截/单挂放行/双挂 503/**pass+超时放行/拒绝+超时拦截**;真实 key 冒烟一条 |
| B3 | 统一审核闸门接入 | `services/content_security.py` 的 `audit_user_text`/`audit_user_image` 两公共入口 + `routers/auth.py`(注册昵称补审) | **分流在两个入口统一做**(按服务端身份判定,已接的 8 个 router 自动全覆盖:posts/lostfound/news/courses/users/messages/feedback/upload);微信文字 msg_sec_check/图片 img_sec_check 不动;非微信走 L1+L2;缺身份数据不放行;**注册/OAuth 初始昵称补审**(auth.py 现零调用点);编辑走合并后内容再审;**>2500 字完整分段审或拒**(微信 `content[:2500]` 截断不再裸放尾部);kill-switch `ENABLE_CONTENT_MODERATION=false` 全局直放——保留但 iOS 提审前必须 true(prod 现状 true,2026-09-11 az 实查);日志挂 hkmu 家族 stdout handler | 邮箱用户发违规词帖→拦截(现在会成功=bug 修复);违规注册昵称被拒;编辑把违规词塞进旧帖被拦;**尾部超长违规内容被拦**;正常帖不受影响;既有 159 测试基线不红 |
| B4 | 用户拉黑 API | `database.py`(blocks 表,DDL 注释**无分号无引号**)+ `routers/users.py` 端点 | POST/DELETE /users/me/blocks + GET 列表;**过滤面(9-11 复核)**:feed/顶层评论/**评论回复批量查询/引用帖摘要/详情直达/课评/新闻评论/失物/用户搜索推荐**——读取入口接入当前查看者,分页前统一过滤,计数同步;被屏蔽父评论与「回复@某人」展示规则定案;**匿名帖拉黑走 post_id**:服务端解析作者,查看者不接触 author_id(现状 `posts.py:123-127` 匿名对非 admin/本人置 null,按 user_id 拉不了匿名者);私信会话过滤被拉黑者 | 单测:拉黑后 feed 不见其帖、私信不可再发,取消恢复;**匿名帖可拉黑且生效;回复/引用/搜索面不见被拉黑者** |
| B5 | Sign in with Apple | `routers/auth.py` 新 `POST /auth/apple` + 新 `services/apple_service.py` | 照 Google handler 三步模板;JWKS(`appleid.apple.com/auth/keys`)+RS256 验签,校验 iss/aud(=env 配置**精确值**白名单)/exp;**nonce 或 jti 单次消费**(防 identity token 重放);**sub 为唯一稳定账号键**(relay 邮箱不可依赖;`email_verified` 严格解析,字符串 `"false"` 不当已验证;合法无邮箱身份放行);name 仅首次授权给,缺失兜底 `nickname`;并发首次登录唯一冲突回读;**防覆盖守卫全登录口共用(Google/Apple/邮箱)**:匹配到已有其他 provider 不静默覆盖,且单 OAuth 槽未扩展前不提供完成不了的绑定引导;**必须带 tests(现状 OAuth 零覆盖)** | 单测:合法 token 建号/登录、错 aud 拒、已有 Google 账号邮箱匹配不覆盖、**同一 token 重放第二次被拒、无 email 声明可建号(sub 键)** |
| B6 | 推送 token 骨架 | `database.py`(push_tokens 表)+ `routers/users.py` 注册端点 | 存 expo token + platform + user_id;此阶段只入库,不触发;**token 归属三规则(9-11 复核)**:登出即失效、换账号原子迁移(同设备 A→B 切换 token 归 B 不串推)、注销连带清空(接 B9) | 单测注册/去重 + **同设备 A 登出→B 登录后 token 归属切换正确** |
| B7 | 小修 | `routers/posts.py`/`lostfound.py`/`users.py` | post/失物 create 的 `image_url` 补 `is_module_image_url` 桶校验(对齐评论);删 users.py 旧头像注释 | 单测:外链 image_url 被拒 |
| B8 | 官方联系方式(运营) | 商店材料/协议页 | 占位邮箱换官方邮箱 | 页面可见真实邮箱 |
| B9 | **账号删除(注销)**(9-11 复核新增,App Store 5.1.1(v) 硬要求) | `routers/users.py` 新 DELETE 端点 + 数据处置;与 `docs/ops/隐私合规-差距与路线图-20260906.md` §3.1 注销政策合并施工 | **提供账号注册的 App 必须 App 内可发起删除**;流程:App 内发起→身份确认→异步处置(公开内容按政策删除或匿名化、私信删、会话/推送 token 全失效)→回执;Apple 登录账号须同时撤销 Apple 凭证(token revocation);时限与保留期按隐私路线图 §3.1 法务复核稿 | 单测:注销后 JWT 全失效、push token 清空、公开内容按策略处置、Apple token 撤销调用发出;重复注销幂等 |

## 2. 阶段二:RN 骨架 + 登录 + 核心三件套

**分支** `feature/ios-app` · **工期** vibe 3-4 天 · 新顶层目录 `ios-app/`(React Native/Expo,**独立于 frontend/,共享的只有后端 REST**)

| # | 任务 | 要点 | 验收 |
|---|---|---|---|
| A1 | Expo 工程初始化 | Expo Router + 导航骨架 + 主题(对齐现有蓝绿视觉)+ **i18n 三语(直接复用现有翻译 JSON)** | Expo web 预览可切三语言 |
| A2 | api 层 + JWT | fetch 封装(指 Azure SEA base)+ `expo-secure-store` 存 token + 401 单例 refresh(对齐 web `api.js` 模式) | 登录态跨启动保持 |
| A3 | 登录三件套 | 邮箱+密码(验证提示)/ Google(expo Google Sign-In,后端 `/auth/google` 复用)/ Apple(expo-apple-authentication → `/auth/apple`) | 三路登录真机可用;`/auth/config` 门控 Google 显示 |
| A4 | 资讯流+社区列表 | home/community 两列表页,复用 REST | 下拉刷新/分页/图片懒加载正常 |
| A5 | 帖子详情+评论 | 含评论回复(2026-09-03 上线的能力) | 发评论/回复/匿名逻辑与 web 一致 |
| A6 | 发布器 | 图片选取+压缩(expo-image-manipulator 对齐 web 尺寸档)→ `FormData POST /upload?module=` → 发帖 | 发图文帖全链路;审核拦截的错误态展示 |

## 3. 阶段三:全量页面 + 推送(planner 是关键路径)

**分支** 同上续 · **工期** vibe 4-6 天

| # | 任务 | 要点 | 验收 |
|---|---|---|---|
| A7 | 失物/新闻/课评 | 三套列表-详情(失物含发布) | 对齐 web 功能面 |
| A8 | 私信 | **先 3s 增量轮询**(直接搬 web 已验证方案:page1+seenIds 过滤);会话列表+聊天页 | 双机实测消息自动刷新 |
| A9 | **Planner(拆三步)** | A9a 专业级联选择器(107 专业)/ A9b 三语搜索(searchFold 归一逻辑复用后端已有,前端对齐)/ A9c 学分池+毕业规则展示(REST 复用) | 三语搜索命中/学分池计算与 web 一致 |
| A10 | profile/设置/协议页 | 协议文本用 2026-09-06 修订版;举报入口(FR4 后端复用) | 全功能可达 |
| A11 | 推送接通 | expo-notifications;后端在评论被回复/收到私信时触发(消费 B6 token 表);EAS 凭证配置 | 真机收到离线推送 |

## 4. 阶段四:TestFlight(路线 A)

**工期** vibe 2-3 天 + 审核
- EAS Build(iOS,免 Mac)+ 云签名 + 上传 TestFlight;Beta 审核(松)
- 种子用户 = 香港同学若干;**先跑 §0 假设验证的结论决定投放话术**
- 测试自动化配方:`Expo web 预览秒级走查 + Codex build-ios-apps 模拟器视觉验证`(等价 miniprogram-automator 的角色,先搭再用)

## 5. 阶段五:外区提审(路线 B)

**工期** 材料 0.5 天 + 首审 2-7 天(备 3-4 周长尾)

- [ ] App 中性名定稿(去官方化,备 2-3 候选)+ 描述声明"学生独立开发、与校方无隶属"
- [ ] 隐私标签(App Privacy 如实填:邮箱/openid 映射、图片、遥测)
- [ ] 截图 + **审核测试账号**(微信 4.5 教训:必填,`hkmu_review` 同思路建 iOS 侧)
- [ ] UGC 六件套自查:①过滤(B1-B3)②举报(FR4)③拉黑(B4)④联系方式(B8)⑤年龄分级(17+)⑥**账号删除(B9,5.1.1(v))**
- [ ] 5.2.1 预案:如被拒 → 提供主任背书信(如已到手)/ Resolution Center 英文说明独立非官方性质
- [ ] 上架区域:香港(+其他外区),**排除中国大陆**

## 6. 协作与登记

- 后端模块全部在 SYF 名下(courses/auth/messages 等 owner),无跨人协调;`module-registry.json` 增补 `iOS App` 模块(owner: SYF)后跑 `sync-ownership.sh`
- commit 格式:`[ios] feat/fix: 描述`;共享基础文件(content_security.py/database.py/auth.py)改动群内知会
- 每阶段完结:更新本文档勾选状态 + progress.json

## 7. 里程碑速查

| 里程碑 | vibe·现实档 | vibe·全职档 |
|---|---|---|
| 后端合规就绪(B1-B9) | 2-3 天 | 1.5 天 |
| 0 → TestFlight 可装 | ~2-3 周 | ~1.5-2 周 |
| 0 → 外区过审 | **~3-4.5 周** | **~2.5-3 周** |
| 国区(阶段 2,挂起) | ~3-4 个月,等企业主体+备案 | — |
