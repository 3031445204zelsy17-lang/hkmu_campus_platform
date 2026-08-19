# HKMU Campus · iOS App 技术栈评估

> **2026-07-31 · arch-check（三子代理交叉验证）**
> 评估目标：为 HKMU 校园平台新增 iOS App 的 **技术栈 + 开发成本 + Codex 协作**。
> 代码现状：微信小程序（审核中）+ 网页 PWA + FastAPI/Supabase 后端（就绪）。
> 决策者：学生个人开发者（JS 熟 / Swift 未知 / 预算敏感 / 人力有限）。

## 1. 背景与目标
HKMU 校园平台是多端架构（后端共享）：
- **微信小程序**（内地生端口，正式版审核中）
- **iOS App**（本次评估对象，上 App Store）
- **网页 PWA**（现有）
- **Android**（后续）

iOS 端要解决：选什么技术栈、开发成本（时间/技术/金钱）、怎么和 Codex 协作。

## 2. 现有栈（iOS 复用基础）
| 层 | 现状 |
|---|---|
| 后端 | FastAPI + asyncpg + Supabase Postgres + Azure Web App（海外 SEA），REST + JWT + WebSocket 就绪 |
| 网页前端 | 原生 HTML/CSS/JS + Tailwind CDN（非 React/Vue）|
| 小程序 | 原生微信框架 |
| 其他 | i18n 三语言、Supabase Storage 图片、私信 WS（已降级轮询）|

⇒ **JS/TS 技能 + Supabase JS SDK + FastAPI REST** 是 iOS 端可复用的核心资产。

---

## 3. 四栈对比矩阵（2026-07-31 实测）
| 维度 | Capacitor 套壳 | **RN+Expo ⭐** | Flutter | SwiftUI 原生 |
|---|---|---|---|---|
| 2026 版本 | 8.4.2（07-14）| RN 0.76+ / Expo SDK 53+ | 3.44（Impeller 稳定）| Swift 6.3.3 / iOS 26 |
| 复用现有 PWA/JS | **95%** ✅✅ | 逻辑 70-80% ✅ | 低（Dart）❌ | 0 ❌ |
| Apple 审核 | **4.2 高风险** ⚠️ | 低（无歧视）✅ | 低 ✅ | 最低 ✅ |
| Supabase 集成 | supabase-js ✅ | supabase-js ✅ | supabase_flutter 2.16.0 ✅ | supabase-swift v2.54.1 ✅ |
| 学习曲线（JS 熟）| 近零 ✅ | 平 ✅ | 中 | 陡 ❌ |
| Android 扩展 | ✅ 同码 | ✅ 同码 | ✅ 同码 | ❌ 另写 Kotlin |
| 免 Mac | ❌（云可）| **✅ EAS 云构建** | ❌ | ❌ |
| WebSocket 私信 | WKWebView（ITP 小坑）| 内置 ✅ | web_socket_channel ✅ | URLSessionWebSocketTask ✅✅ |
| CC/Codex 主场 | CC 强 | **CC 强** | 中 | Codex 强 / CC 中 |
| 0→提审周期（15-20h/周）| **1-3 周** | 5-8 周 | 7-11 周 | 8-14 周 |

**Apple 审核关键**：
- **4.2 Minimum Functionality 对套壳（Capacitor/WebView）= 高风险**，持续执行（2025-26 多起实操被拒）。能过，但必须加原生功能（推送/相机/生物识别）+ 本地 bundle + 第三方登录带 Sign in with Apple。
- **RN / Flutter = 无系统性歧视**（美国 Top 500 App 占比 RN 12.57% / Flutter 5.24%，大量在架即按质量审）。

---

## 4. 技术栈推荐

### 🥇 RN + Expo（首选）
- **复用**：JS/TS 逻辑（API、业务模型、状态）直接复用；supabase-js 最成熟（和网页同 SDK）。
- **审核**：Apple 无歧视，低风险。
- **免 Mac**：EAS 云构建（免费 15 iOS builds/月）+ 云签名 + 云上传 TestFlight，**全程不碰 Mac**。
- **Android**：同代码库，后续零成本扩展。
- **CC 主场**：JS/TS 是 Claude Code 强项（1M 上下文扛大工程）。
- **代价**：UI 要用 RN 组件重写（不能搬 HTML/CSS/DOM）。5-8 周。

### 🥈 Capacitor 套壳（最快）
- **复用**：现有 PWA 95% 直接套，1-3 周上线。
- **代价（4.2 墙）**：纯套壳大概率被拒，**必须**：本地 bundle（不远程加载 URL）+ 接 1-2 个原生插件（推送最关键）+ 第三方登录带 Sign in with Apple。
- 适合"最快验证 + 愿意加原生功能过审"。

### ❌ SwiftUI 原生 / Flutter（不推荐）
- **SwiftUI**：0 复用 + 无 Android + 学习陡（Swift 6 强并发）。仅当"只做 iOS 且 Codex 主写"时考虑。
- **Flutter**：Dart 不复用现有 JS，对学生 JS 栈无优势。

---

## 5. 成本评估

### 金钱（起步 ¥800/年）
| 项 | 费用 | 说明 |
|---|---|---|
| Apple Developer（个人）| **$99/年** | 免 DUNS，24-48h 过审，卖家=个人名 |
| Apple Developer（公司）| $99/年 | 需 DUNS + 营业执照 |
| Apple Enterprise | $299/年 | 仅内部分发，**不上 App Store** |
| Xcode / Flutter / Capacitor 工具 | **免费** | — |
| Expo EAS Build | 免费 15 iOS/月；Pro $19/月 | 仅 RN+Expo，免 Mac |
| Codemagic | 免费 500 macOS min/月 | Flutter/Capacitor |
| Mac | RN+Expo 可免；其他要 Mac 或云 Mac $20-139/月 | 黑苹果违法（EULA）|
| APP 备案（仅国区）| 代办 300-1500 + 服务器境内 | 工信部 105 号文 |
| 软著（建议）| ~300 元 | 名称须=备案名=App Store 名 |

⇒ **起步 $99 + 免费工具 ≈ ¥800/年**（RN+Expo 免 Mac）。

### 时间（15-20h/周，中等 App：列表+登录+详情+推送）
| 栈 | 0→提审 | 复用 PWA |
|---|---|---|
| Capacitor 套壳 | **1-3 周** | UI 95-100% / 逻辑 95-100% |
| RN+Expo | 5-8 周 | UI ~10% / 逻辑 70-80% / API 90% |
| Flutter | 7-11 周 | UI 0 / 逻辑 ~20% |
| SwiftUI | 8-14 周 | 0 |

Apple 审核周期：首次 2-7 天（长尾 3-4 周）；更新 1-2 天。第一大拒因 4.3 Spam ≈ 28%。

### 技术（学习曲线 / 维护）
| 栈 | demo/生产小时（JS 熟）| 长期维护 |
|---|---|---|
| Capacitor | ~6h / ~30h | 4.2 拒审可控（加原生插件）；跨平台一套 |
| RN+Expo | ~20h / ~100h | 低；expo-* 成熟；跨平台 |
| Flutter | ~25h / ~120h | 低；但 JS 逻辑要重写 Dart |
| SwiftUI | ~45h / ~150h | 单端 iOS，无跨平台红利 |

---

## 6. Codex 协作（用户记忆准确 ✅）

### "Codex iOS 插件"真相
**OpenAI Codex 真有 `build-ios-apps` 插件**（非混淆）：
- 安装：Codex app → Plugins → 搜 "build-ios-apps"。
- 能力：给 Codex "模拟器里的眼睛"——写 SwiftUI、启动模拟器、截图、点按钮、读 UI 交互验证。背后 MCP server 驱动 `xcodebuild` + 模拟器。
- **Xcode 26.3（2026-02-03 RC）官方原生集成 Claude Agent + Codex**（走 MCP），可改工程设置、捕 Xcode Previews、迭代 build/修错。

⚠️ 三个易混概念要分清：
1. **OpenAI Codex `build-ios-apps`**（用户记的）— **真存在**
2. **GitHub Copilot for Xcode**（2024 GA）— GitHub/微软的，**不是 Codex**
3. **Xcode 26.3/27 原生 Agent** — Apple 把 Claude + Codex 都收进 IDE

### 各栈 CC/Codex 支持度
| 栈 | Claude Code | Codex |
|---|---|---|
| SwiftUI 原生 | 中 | **强**（build-ios-apps + 视觉闭环）|
| RN/Expo（JS）| **强**（1M 上下文）| 中-强 |
| Flutter（Dart）| 中 | 中（插件对 Flutter 有 issue）|
| Capacitor（Web JS）| **强** | 中 |

### CC + Codex 双工具分工（iOS）
基于 cc-codex-division 方法论（CC 量大扛执行 / Codex 量少用在刀刃=视觉/原生/架构）：

| 谁主写 | 任务 | 理由 |
|---|---|---|
| **Codex 主写** | SwiftUI 视图层、原生模块、模拟器 UI 迭代 | 视觉闭环 + CC 没有的原生能力 |
| **CC 主写** | 业务逻辑/网络/状态、跨平台 JS（RN/Capacitor）、共享后端、长上下文重构 | 1M 上下文 + agent 编排 |
| **Codex review CC** | UI 渲染正确性、原生 API 用法 | 不同视角 + 视觉验证 |
| **CC review Codex** | 跨文件一致性、工程结构、边界 | 长上下文审大 diff |

⇒ **走 RN+Expo 时**：CC 扛主线（JS/TS），Codex 只在原生桥接/原生模块上场。
⇒ **走 SwiftUI 时**：Codex 主写（视觉强），CC review 一致性。

### iOS 工作流（Xcode 依赖）
- **原生 iOS：Xcode 是硬依赖**（签名/Archive/上架/真机调试）。Xcode 26 自 2026-04-28 起提审强制。
- **CC/Codex 能做**：`xcodebuild` + `xcrun simctl` + **fastlane** 自动化 build/sign/archive/upload TestFlight。已有现成 Claude Code fastlane skill。
- **跨平台栈（RN/Flutter/Capacitor）Xcode 依赖最轻**：大部分开发不碰 Xcode，只原生模块/发布时用。

---

## 7. ⚠️ 国区合规墙（最关键）

**App Store 国区 + 个人主体 + UGC（论坛/私信/资讯）+ APP 备案 = 扛不住**：
- 工信部 105 号文：App Store 中国区上架强制 **APP 备案号**（2024-03 起）。
- APP 备案要境内主体 + **服务器必须在大陆**（HK/Azure 海外办不了）。
- 个人主体仅非经营性；UGC/IM/资讯各需额外资质（个人拿不到）。

⇒ **iOS 现实路径**（和「小程序先体验版」同逻辑）：
| 路径 | 首年成本 | 可承载功能 | 推荐度 |
|---|---|---|---|
| **A. TestFlight / 非国区 App Store** | ~$99 | 全功能 UGC+IM+资讯 | **学生首选** |
| B. 国区 + 个人 APP 备案 | ¥800-1500 | 仅非经营、无 UGC | 不适用（砍不到）|
| C. 国区 + 企业主体 | ¥3000-8000/年 | 全功能 + 资质 | 阶段 2 |

**建议**：iOS 先走 **TestFlight / 非国区**（$99/年，全功能，学生现在能上）→ 国区等企业主体 + APP 备案 + 数据境内（和小程序正式版同一个阶段 2）。

---

## 8. 该动 / 别动清单

🔴 **立刻定**：
- ① 技术栈：RN+Expo（推荐）／ Capacitor（最快）
- ② 上架范围：TestFlight+非国区（现在能上）／ 国区（等企业主体）

🟠 **稳定后**：
- 注册 Apple Developer $99/年
- RN+Expo → EAS 免 Mac 构建
- Capacitor → 必接推送插件过 4.2

🟢 **优化时**：
- Codex build-ios-apps 插件（原生/SwiftUI 迭代）
- fastlane 自动化 TestFlight

⬜ **别动**：
- SwiftUI 从零重写（对学生 + JS 栈 + 要 Android，性价比最低）
- 黑苹果（违反 Apple EULA）
- 国区个人 APP 备案 + UGC（扛不住，别浪费时间）

---

## 9. 综合建议
**RN+Expo + 先 TestFlight/非国区**：
- 复用 JS 技能 + 免 Mac + 低审核 + Android 同代码 + CC 主场/Codex 原生辅助。
- 国区 UGC 墙等企业主体再碰（和小程序正式版一起，阶段 2，反正都是同一堵墙）。

---

## 10. 来源（权威，截至 2026-07-31）
**Apple 审核 / 费用**：
- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Apple Developer Programs](https://developer.apple.com/programs/)
- [Xcode 26.3 agentic coding（2026-02）](https://www.apple.com/newsroom/2026/02/xcode-26-point-3-unlocks-the-power-of-agentic-coding/)

**Apple 4.2 套壳**：
- [Mobiloud: WebView wrapper 审核](https://www.mobiloud.com/blog/app-store-review-guidelines-webview-wrapper)
- [Newly.app: 为什么 App 被拒（2026）](https://newly.app/how-to/why-apps-get-rejected-from-the-app-store)
- [Capgo: Capacitor 过审指南](https://capgo.dev/blog/capacitor-ota-updates-app-store-approval-guide/)

**框架版本（实证）**：
- [Capacitor 8.4.2](https://capacitorjs.com/)（npm，2026-07-14）
- [supabase-swift v2.54.1](https://github.com/supabase/supabase-swift)（2026-07-29）
- [supabase_flutter 2.16.0](https://pub.dev/packages/supabase_flutter)
- [Expo SDK 53+ 新架构](https://expo.dev/)
- [Flutter 3.44](https://flutter.dev/blog/whats-new-in-flutter-3-44)

**Codex / iOS 工具链**：
- [OpenAI Codex: Build for iOS](https://learn.chatgpt.com/use-cases/native-ios-apps)
- [build-ios-apps 插件安装指南](https://azukiazusa.dev/en/blog/ios-app-development-with-codex)
- [Anthropic: Xcode Claude Agent SDK](https://www.anthropic.com/news/apple-xcode-claude-agent-sdk)
- [CC + fastlane iOS Releases（2026-07）](https://theyawns.com/2026/07/03/claude-code-custom-skills-fastlane-for-ios-releases/)

**国区合规**：
- 工信部 105 号文（APP 备案）
- [Apple 国区 ICP/APP 备案强校验](https://developer.apple.com/cn/help/app-store-connect/reference/app-information/)
- [beian.miit.gov.cn](https://beian.miit.gov.cn)
