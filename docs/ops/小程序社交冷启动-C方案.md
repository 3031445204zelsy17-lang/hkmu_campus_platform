# Phase 4 预览:同校社交冷启动(P0 HKMU 验证+同学推荐 / P1 邀请分享绑定)

> 方案已批准(2026-06-27)。执行时机:**Phase 3 私信 live 验证通过后**启动。
> 8 步实施:C.1 后端 schema → C.2 HKMU 域+bind-email → C.3 关系端点 → C.4 app.js+social.js → C.5 profile → C.6 new-chat → C.7 home 消费+i18n → C.8 验证。

## Context

Phase 3 私信(DM)代码已完成(待 live 验证),但**冷启动是空的** —— 新用户进来没人可聊。微信好友关系链对普通小程序**设计层不可用**(已核实,见 memory `wechat-friend-graph-unavailable`),所以"开箱即有熟人"只能靠自有关系图。本方案两条互补路径,复用刚做好的 DM:

- **P0 同校**:用 HKMU 邮箱验证身份 → 解锁"同校标识 + 同学推荐",点推荐直接 DM。
- **P1 邀请**:每人生成邀请码 → 分享小程序卡片给微信好友 → 对方落地 → **自动双向好友** → 直接 DM。

**已锁决策**:P1 落地即自动好友(DM 本就开放,好友只管"发现/置顶",不授新权限,风险低);P0 分层(微信/任意邮箱照常注册,HKMU 邮箱验证是可选验证层,不破坏现有)。

## 现状(已勘探)

- `users` 表有 `email`/`student_id`(UNIQUE 可空)/`programme_code`(C3 加);`email_verified BOOLEAN DEFAULT TRUE`(⚠️ ≠ HKMU 验证);**无** `intake_year`/`invited_by`;**无好友表**。
- 邮箱验证基建完整:`/auth/email/register`(EmailRegister: email regex 通用、无域名白名单)+ `/auth/verify-email`(token 一次性,置 email_verified=TRUE)+ `email_tokens` 表。
- `student_id` 现靠手填;HKMU 学生邮箱前缀 `s1234567` 即学号 → **可自动推导**。
- 私信纯 ad-hoc partner_id(无 conversations/friends 表),DM 对任何人开放。
- 小程序 `app.js` 不读启动 query;**全项目零分享配置**;profile action-row 有空位;new-chat `nc-user` 列表可复用;chat.js onLoad 收 `user_id`(P1 落地可直跳)。

## Architecture

### 后端(`backend/`)

**1. Schema(`database.py`,幂等 `DO $$ IF NOT EXISTS $$`,沿用 C3 模式)**
- `ALTER TABLE users ADD COLUMN hkmu_verified BOOLEAN DEFAULT FALSE;`
- `ALTER TABLE users ADD COLUMN invite_code TEXT;`(+ 唯一索引,懒生成)
- 新表 `friendships`:
  ```sql
  CREATE TABLE IF NOT EXISTS friendships (
      id SERIAL PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'accepted',   -- P1 自动=accepted;留枚举备将来 friend-request
      source TEXT DEFAULT 'invite',
      created_at TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE(user_id, friend_id)
  );
  ```
  存储约定:每次建立关系插**两行**(user_id→friend_id 和 friend_id→user_id),双向查询只需 `WHERE user_id=me`。

**2. `models.py`**
- `UserOut` 加 `hkmu_verified: bool = False`、`invite_code: Optional[str] = None`。
- 新:`BindEmail { email }`(服务端 HKMU 域校验)、`InviteCodeOut { invite_code, share_path }`、`FriendshipOut { id, friend: UserOut, source, created_at }`、`SuggestOut`(= UserOut + `reason: Optional[str]`)。
- `EmailRegister` 保持通用 pattern(分层:非 HKMU 邮箱仍可注册,只是不解锁验证层)。

**3. `routers/auth.py` + `services/auth_service.py`**
- HKMU 域判定 helper `is_hkmu_email(email)`:`@hkmu.edu.hk`(教职员)/`@live.hkmu.edu.hk`(学生)。
- `verify_email` 消费 token 时:**若 email 是 HKMU 域 → 同时置 `hkmu_verified=TRUE`**;学生邮箱前缀(去前导 `s`)→ 回填 `student_id`(若空)。
- 新 `POST /users/me/bind-email`(auth):已有账号(如微信登录用户)补绑 HKMU 邮箱 → 校验域 → 复用 email_tokens 发验证 → verify-email 落库(email+hkmu_verified)。

**4. `routers/users.py`(SYF 模块,新端点)**
- `GET /users/me/invite-code`(auth):懒生成 invite_code(8 位 base62,唯一),返回 `{invite_code, share_path: "/pages/home/home?inv=<code>"}`。
- `GET /users/suggest?limit=10`(auth):候选 = `hkmu_verified=TRUE AND id<>me AND id NOT IN (我的 friend_id) AND id NOT IN (我的会话 partner_id)`;同 `programme_code` 优先排序;返回 `SuggestOut[]`(带 `reason` 如"同专业 · DSAI"/"HKMU 同学")。
- `GET /friendships`(auth):我的 accepted 好友(`WHERE user_id=me AND status='accepted'`)→ `FriendshipOut[]`。
- `POST /friendships/invite`(auth)body `{invite_code}`:解析 → inviter;**自邀拦截**(inviter==me → 200 no-op);插两行(`ON CONFLICT DO NOTHING` 幂等)→ 返回 `{friend: inviter UserOut, created: bool}`。(P1 自动好友核心)
- `_USER_COLS` / `_user_row_to_out` 加 `hkmu_verified`、`invite_code` 字段读取。

**5. `routers/messages.py`** — **不改**(DM 维持 ad-hoc partner_id)。

### 前端(`miniprogram/`)

**6. `app.js`(共享,加 query 读取 — 群通知)**
- `onLaunch(options)` / `onShow(options)`:`options.query.inv` → `globalData.pendingInvite = code`(仅暂存,不在此消费)。

**7. 新 `utils/social.js`**(传输层,仿 messages.js 风格)
- `getInviteCode()`(GET /users/me/invite-code)、`buildSharePath()`、`consumeInvite(code)`(POST /friendships/invite,自邀 no-op)、`fetchFriends()`、`fetchSuggest()`。

**8. `pages/home/home.js`(司徒模块 — PR review)**
- onShow:`globalData.pendingInvite` && 已登录 → `consumeInvite(code)` → 清暂存 → toast"已与 X 成为好友" + 可选跳 `chat?user_id=X`。

**9. `pages/profile/profile.js + .wxml`**
- `hkmu_verified` 徽章。
- 未验证 → "验证 HKMU 邮箱"入口(bind-email 流程:输邮箱 → 后端发验证 → toast)。
- "邀请好友"分享按钮(`<button open-type="share">`)+ `onShareAppMessage` 返回 `{title, path: buildSharePath(), imageUrl?}`。

**10. `pages/new-chat/new-chat.js + .wxml`**(搜索页顶部加两段,复用 `nc-user` 渲染)
- "我的好友"(fetchFriends)→ 点选 openUser → chat。
- "可能认识的同学"(fetchSuggest,带 reason 副标题)→ 点选 → chat。
- 原搜索框/结果保留在下方。

**11. `pages/messages/messages.wxml`** — 轻量:新好友 toast 即可(P1 自动好友,无请求队列)。

**12. i18n(`utils/i18n.js`,SYF 模块)** — 新 `social` scope 三语:bindEmailTitle/bindEmailHint/bindEmailSent/verifyFail/inviteTitle/inviteShareTitle/inviteSuccess/friendsTitle/suggestTitle/suggestReason* 等。

## 复用(别重造)
- 邮箱验证:`auth.py` `email_tokens` + `/auth/verify-email`(C.2 扩展)。
- `utils/request.js` `request({method,path,data,auth})`。
- new-chat `nc-user` 列表渲染(C.6 复用)。
- `chat.js` onLoad `user_id` 契约(P1 落地直跳)。
- DM ad-hoc partner_id(不变)。
- `getInitial`/`resolveUrl`(头像 fallback)。

## 验证(静态 + live)
- **后端静态**:`python -m py_compile backend/app/*.py routers/*.py services/*.py`;启动建表确认 `friendships`/新列。
- **后端 live**(curl,带 Bearer):`/users/me/bind-email` 非 HKMU 域 → 400;HKMU 域 → 发验证;verify 后 `hkmu_verified=TRUE` + student_id 回填;`/users/suggest` 返回同 programme 候选 + reason;`/friendships/invite {invite_code}` 幂等建双向 + 自邀 no-op。
- **前端静态**:node --check ×N + i18n 三语 social scope parity + WXML 平衡 + app.js query 解析。
- **E2E**:① A 用 HKMU 邮箱注册+验证 → new-chat 推荐 看到 B(同 programme)→ DM;② A profile 点"邀请好友"→ 分享卡片 → B(新微信号)落地 home → 自动好友 toast → B new-chat"我的好友"看到 A → DM;③ 微信老用户 C 在 profile 补绑 HKMU 邮箱 → 解锁推荐。

## 风险与协作
- **跨人**:`home.js`(消费邀请)属司徒模块 → PR review;`app.js` 共享 → 群通知。其余后端(users/auth)+ 前端(new-chat/profile/social)均在 SYF 自有模块。
- **student_id 回填**:仅当 users.student_id 为空时由学生邮箱前缀回填,不覆盖用户已填值。
- **自邀**:前后端双拦(invite_code 解析==me → no-op)。
- **生产 curl 探活**可能受本地 VPN 挡(memory `vpn-azure-https-block`);非代码问题,换热点/节点。

## 不做(v1 范围外)
- 小程序码生成(`wxacode.getUnlimited`,需 mp access_token,v2)。
- friend-request 确认流(P1 已定自动好友;`status` 枚举留作将来)。
- 手机通讯录匹配(P3,需企业主体+认证+付费)。
- 入学年份聚类(HKMU 学号年份编码未确认;v1 用 programme_code + identity 已够"同学"信号)。
- APP 版本(将来用 unionid 统一账号,好友关系表同 schema 迁移)。
