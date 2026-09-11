# HKMU Campus · iOS 开发计划(执行版)

> **活文档** · 建版 2026-09-07 · 栈/路线/登录/审核选型已全部定案,本文档是唯一执行入口
> 决策依据(只读存档,不再更新):
> - `docs/ops/iOS端技术栈评估.md`(2026-07-31,四栈对比)
> - `docs/ops/iOS上架路线对比-外区vs国区-20260907.md`(路线/标准/红档核实/周期)
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

**开工日刷新清单(半天,时效项)**:Expo SDK 当前版 / EAS 免费额度(15 iOS builds/月?)与排队时长 / EAS Xcode 26 镜像 / OpenAI 新号开 moderation key 是否需绑卡 / Apple Developer 注册付款方式。

---

## 1. 阶段一:后端前置合规(不依赖 iOS 决策,现存风险修复)

**分支** `feature/ios-backend-compliance` · **工期** vibe 1-2 天 · **CI** pytest 门禁全绿(本地跑法见 memory:brew postgres env 覆盖)

| # | 任务 | 模块/文件 | 约束 | 验收标准 |
|---|---|---|---|---|
| B1 | L1 本地审核引擎 | 新 `backend/app/services/moderation_local.py`;词表 `backend/app/resources/sensitive_words*.txt`(konsheng MIT 裁剪版,不入全量 GFW 表) | OpenCC t2s 归一 → Aho-Corasick/trie 匹配;进程内零网络;启动加载一次;命中返回类别 | 单测:繁体变体命中简体词表;正常校园帖零误杀样本通过 |
| B2 | L2 远程审核双活 | 新 `backend/app/services/moderation_remote.py` | OpenAI moderation + 阿里国际站 SG 两 client;**任一 pass 即放行,双挂才 fail-closed**;超时 10s(沿用 stable_token 教训);key 走 env,无 key 的 provider 跳过不炸 | mock 单测覆盖:单挂放行/双挂拦截/正常放行/命中拦截 四路;真实 key 冒烟一条 |
| B3 | 统一审核闸门接入 | `services/content_security.py` + `routers/posts.py`/`upload.py`/`lostfound.py` 现有调用点 | 微信用户路径不动(imgSecCheck);**非微信用户改走 L1+L2**;语义保持 fail-closed;日志挂 hkmu 家族 stdout handler | 邮箱用户发违规词帖 → 拦截(现在会成功=bug 修复);正常帖不受影响;既有 159 测试基线不红 |
| B4 | 用户拉黑 API | `database.py`(blocks 表,DDL 注释**无分号无引号**)+ `routers/users.py` 端点 | POST/DELETE /users/me/blocks + GET 列表;帖子流/评论/私信会话过滤被拉黑者 | 单测:拉黑后 feed 不见其帖、私信不可再发;取消恢复 |
| B5 | Sign in with Apple | `routers/auth.py` 新 `POST /auth/apple` + 新 `services/apple_service.py` | 照 Google handler 三步模板;JWKS(`appleid.apple.com/auth/keys`)+RS256 验签,校验 iss/aud(=`APPLE_BUNDLE_ID` env)/exp;**防覆盖守卫:邮箱匹配到已有其他 provider 时不静默覆盖**(返回需绑定引导);`nickname` NOT NULL 用 Apple name 或兜底;**必须带 tests(现状 OAuth 零覆盖)** | 单测:合法 token 建号/登录、错 aud 拒、已有 Google 账号邮箱匹配不覆盖 |
| B6 | 推送 token 骨架 | `database.py`(push_tokens 表)+ `routers/users.py` 注册端点 | 存 expo token + platform + user_id;此阶段只入库,不触发 | 单测注册/去重 |
| B7 | 小修 | `routers/posts.py`/`lostfound.py`/`users.py` | post/失物 create 的 `image_url` 补 `is_module_image_url` 桶校验(对齐评论);删 users.py 旧头像注释 | 单测:外链 image_url 被拒 |
| B8 | 官方联系方式(运营) | 商店材料/协议页 | 占位邮箱换官方邮箱 | 页面可见真实邮箱 |

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
- [ ] UGC 五件套自查:①过滤(B1-B3)②举报(FR4)③拉黑(B4)④联系方式(B8)⑤年龄分级(17+)
- [ ] 5.2.1 预案:如被拒 → 提供主任背书信(如已到手)/ Resolution Center 英文说明独立非官方性质
- [ ] 上架区域:香港(+其他外区),**排除中国大陆**

## 6. 协作与登记

- 后端模块全部在 SYF 名下(courses/auth/messages 等 owner),无跨人协调;`module-registry.json` 增补 `iOS App` 模块(owner: SYF)后跑 `sync-ownership.sh`
- commit 格式:`[ios] feat/fix: 描述`;共享基础文件(content_security.py/database.py/auth.py)改动群内知会
- 每阶段完结:更新本文档勾选状态 + progress.json

## 7. 里程碑速查

| 里程碑 | vibe·现实档 | vibe·全职档 |
|---|---|---|
| 后端合规就绪(B1-B8) | 1-2 天 | 1 天 |
| 0 → TestFlight 可装 | ~2-3 周 | ~1.5-2 周 |
| 0 → 外区过审 | **~3-4.5 周** | **~2.5-3 周** |
| 国区(阶段 2,挂起) | ~3-4 个月,等企业主体+备案 | — |
