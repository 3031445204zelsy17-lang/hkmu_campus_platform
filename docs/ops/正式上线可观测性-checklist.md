# 正式上线 — 可观测性 Checklist

> 适用阶段:最初 ≤1000 注册用户、慢增长。本文回答:**访问量/流量/性能超载/安全 从哪里看、怎么看、看完怎么办。**
> 最后更新:2026-07-02

## 0. 量级判断(先定调)

- 1000 注册 ≠ 1000 并发。校园产品典型同时在线远低于注册数,**峰值并发大概率几十~一两百**。
- 这个量级**当前免费层架构基本扛得住**,重心是「**先观测,再扩容**」——用数据告诉你什么时候该升,而不是现在就盲目升付费层。
- **唯一确定性崩点**:Supabase 免费层 auto-pause(已有 keepalive 每 10min ping 缓解,但属缓解非根治;pause 了服务 503,memory supabase-pause-recovery 有恢复 runbook)。
- 次要隐患:Azure 免费/基础层冷启动(首次请求卡几秒)+ 单实例(无自动扩缩)。

## 1. 4 类数据 → 平台对照

| 类别 | 看什么 | 平台 | 现状 | 路径 |
|------|--------|------|------|------|
| **可用性** | uptime、响应时间、宕机 | UptimeRobot(外部探活) | ✅ 已配 | app.uptimerobot.com |
| | 健康探活 | Azure App Service 健康检查 | ✅ /api/health 真探活 | Portal → Web App → 监视 → 运行状态 |
| **访问量/流量** | DAU、PV/UV、留存(业务) | GA4 + Mixpanel | ✅ 已埋点(I3) | GA4/Mixpanel 后台 |
| | 请求数、QPS、带宽(技术) | Azure Monitor / App Insights | ⚠️ App Insights 未开 | Portal → Web App → Application Insights |
| | 小程序访问 | 微信数据助手 + 运维中心 | ✅ 部分已用 | 微信公众平台 → 数据/运维中心 |
| **性能/超载** | 响应延迟、错误率、CPU/内存 | Application Insights | ⚠️ 未开(**主力缺口**) | 同上 |
| | DB 连接数、慢查询、存储 | Supabase Dashboard | ✅ 现成,要常看 | supabase.com → Project → Reports/Logs |
| **安全** | 异常请求、认证失败、可疑 payload | App Insights(4xx/5xx 模式) + 后端日志 | ⚠️ 弱 | App Insights 失败+日志 ; Azure Log Stream |

## 2. 主力缺口:Application Insights(未开)

progress `internal_beta_readiness.B3` 把它列为「待用户在 Azure 门户启用」。它是后端**性能/超载/错误**的主力观测面。

- **怎么开**:Azure Portal → 你的 Web App → Monitoring → Application Insights → 启用。
- **开了能看**:每分钟请求数、响应时间分布(P50/P95/P99)、失败率(5xx)、最慢的接口 Top N、未处理异常堆栈、按接口聚合。
- **深度 trace**(每个 DB 调用耗时、跨服务链路)需在 FastAPI 集成 OpenTelemetry → **1000 人量级先不做**,基础指标够用;量大或定位疑难时再加。
- 小程序端错误监控已用微信后台运维中心(memory `miniprogram-operations.B3`:getRealtimeLogManager + app.js onError 兜底)。

## 3. 怎么判断「超载了」——具体信号

出现一两个就该考虑扩容(见第 5 节):

- 响应时间 **P95 持续 > 1–2 秒**
- **5xx 错误率 > 1%**
- App Service **CPU 或内存持续 > 70–80%**
- **频繁冷启动**(免费/基础层内存紧张反复重启,表现为间歇性卡几秒)
- Supabase **active connections 接近上限**(免费层很低,Dashboard 直接看)或报 `too many connections`
- Supabase **存储接近 500MB / 带宽接近限额**(免费层)
- UptimeRobot 响应时间**趋势性退化**(不是单点抖动)
- App Service **重启次数**异常升高

## 4. 告警:从「被动看」到「主动通知」

| 对象 | 阈值 | 通道 | 状态 |
|------|------|------|------|
| UptimeRobot 探活 | 端点不可达 | 邮件/微信 | ✅ 已配 |
| App Insights | 失败率 > 阈值 / 响应 P95 > 阈值 | 邮件 | ⚠️ 开了 App Insights 后配 |
| Supabase | 项目接近限额 / 自动 pause | 邮件(Supabase 自动) | ✅ 默认;留意收件箱 |
| App Service | CPU/内存/重启 | 邮件 | ⚠️ Portal 配告警规则 |

## 5. 观测 → 扩容:数据达到什么阈值,升什么

这是「看完数据怎么办」的决策对照(别提前升,按信号升):

| 信号 | 扩什么 |
|------|--------|
| Supabase 连接数常逼近上限 / 频繁 pause | **升 Supabase Pro**(付费层连接数/pause 规则放宽) |
| App Service CPU/内存持续高 / 冷启动频繁 | **升 App Service 标准层 + 多实例 + 自动扩缩** |
| 一旦上多实例 | **必须加 Redis**:① WebSocket 私信跨实例广播(否则跨实例消息丢) ② 顺手做缓存 |
| 请求数大 / DB 压力高 | **加热点读缓存**(课程目录/新闻/feed)+ **全局限流**(公开读端点) |
| 安全:异常请求/注入尝试多 | 收紧 CORS、加全局限流、补日志脱敏 |

> 1000 人量级大概率只会先碰到 Supabase pause 这一项;其余是「量再涨一档」才需要。

## 6. 安全观测(上线前补)

**已有**:HTTPS、参数化 SQL(asyncpg `$N` 防注入)、后端 sanitize + 前端 textContent(XSS)、JWT+refresh、部分速率限制、密钥在 Azure app settings / GitHub secrets。

**上线前补**:
- 依赖漏洞扫描(`pip-audit` / Dependabot)
- CORS 收紧到实际域名
- 全局限流(公开读端点)
- 日志脱敏(不落 token/密码明文)
- 密钥轮换流程
- UGC 内容审核机制(社区/课评/失物/私信——人盯 + 关键词 + 举报)

## 7. 1000 人量级**不需要**的东西

- **Grafana / Prometheus** —— 给多服务集群用的,单实例 + 几百并发纯属增运维负担。各平台原生面板够。
- **K8s / 服务网格监控** —— 同上,用不上。
- **付费 APM(Datadog/New Relic)** —— Azure App Insights 免费层够用。
- **统一聚合面板** —— 等量大、多实例时再考虑 Grafana 聚合 Azure+Supabase+自定义指标。

## 8. 下一步:收敛成 3 件事

1. **开 Application Insights**(Azure 门户,几分钟)—— 补上后端观测主力。
2. **配 2-3 个告警**:App Insights 失败率/响应时间 + UptimeRobot 关键端点(/api/health、/api/v1/courses、/api/v1/news)。
3. **定期(每周)看 Supabase Dashboard** 的连接数和存储——auto-pause 是你唯一的确定性崩点。

做完这 3 件,「访问量 / 流量 / 超载 / 安全」就都有地方看了。量级往上一档(数千 DAU / 多实例)时,再回到第 5 节按信号扩容。
