#!/usr/bin/env bash
# HKMU Campus — 按需健康检查（on-demand）
# 触发：用户说"查一遍情况 / 看下健康"等 → Claude 执行 bash scripts/health-check.sh 并解读。
# 4 段全用真实有数据的源：端点探活 / 后端错误+安全(sec_audit 日志) / App Service 平台指标 / CI。
# 查不了的（GA4 / 微信访问 / 微信错误）需人工看各自面板——脚本末尾提示。
#
# 已知小缺口：App Insights AppRequests（per-route 性能剖析）没附上（init 顺序问题）；
# 但 sec_audit(5xx+path+ip) + 平台指标(Http5xx/Requests/AverageResponseTime) 已覆盖错误/请求/延迟/安全。
#
# 依赖：az（已登录）+ gh（已登录）+ 当前 VPN 能连 Azure（JP/HK 节点）。

set -uo pipefail
HOST="https://hkmu-campus-sea.azurewebsites.net"
RG="rg-hkmu-sea"
APP="hkmu-campus-sea"
CID="9d55bc73-686a-4492-b977-afd2b0bd1740"   # LA workspace hkmu-sea-logs customerId

echo "================= HKMU Campus 健康检查  $(date -u '+%Y-%m-%d %H:%M UTC') ================="

echo
echo "【1/4】端点探活（/api/health 做 DB SELECT 1 → DB 挂则 503）"
for ep in /api/health /api/v1/courses/programmes /api/v1/news /api/v1/users/me; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HOST$ep" 2>/dev/null || echo "ERR")
  printf "  %-32s -> %s\n" "$ep" "$code"
done

echo
echo "【2/4】后端 近1h 错误 + 安全（AppTraces 里的 sec_audit：记 401/403/429/5xx + path + ip）"
echo "  --- 近1h sec_audit 总数（按 status/path/ip 聚合，多的在上）---"
az monitor log-analytics query -w "$CID" -o table --analytics-query \
  "AppTraces | where Message has 'sec_audit' | where TimeGenerated > ago(1h)
   | summarize hits=count() by Message | order by hits desc" 2>&1 | head -12

echo
echo "【3/4】App Service 平台指标 近1h（Http5xx=错误 / Requests=请求 / AverageResponseTime=延迟 / MemoryWorkingSet / CpuTime）"
RID=$(az webapp show -g "$RG" -n "$APP" --query id -o tsv 2>/dev/null)
az monitor metrics list --resource "$RID" \
  --metric Http5xx Requests AverageResponseTime MemoryWorkingSet CpuTime \
  --interval PT1H -o table 2>&1 | head -24

echo
echo "【4/4】CI 最近 workflow runs"
gh run list --limit 6 2>&1 | head -8

echo
echo "⚠️ 查不了的（人工看）：GA4 → analytics.google.com ｜ 微信访问/错误 → 微信公众平台 数据助手/运维中心"
echo "====================================================================================="
