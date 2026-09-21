#!/usr/bin/env bash
# ═══ Azure 花钱透视镜 ═══
# 用法:  bash scripts/cost.sh        (需要先 az login)
# 输出:  ① 在跑资源清单 ② 本月至今花费(按类别) ③ 对照预警线
# 原理:  az resource list(实况盘点) + Cost Management API(权威账单,和扣卡的钱同源)
# 限流:  计费 API 每小时只准查几次,撞 429 脚本会等 20s 重试一次,再撞就等一分钟再跑
# 完整可视化(不受限流影响): portal.azure.com → 成本管理 → 成本分析

set -euo pipefail
SUB_ID="00f0a84b-eda8-4470-8fc2-1b59ca856c72"
BUDGET_USD=25

echo "══ ① 在跑的资源(每行都是活的,都在计费) ══"
az resource list --subscription "$SUB_ID" -o json | jq -r '
  def zh: {
    "microsoft.web/serverfarms":               "App计划(计算,大头)",
    "microsoft.web/sites":                     "网站(蹭App计划,不另计)",
    "microsoft.containerregistry/registries":  "镜像仓库(按天计)",
    "microsoft.insights/components":           "应用监控",
    "microsoft.operationalinsights/workspaces":"日志仓库",
    "microsoft.network/publicipaddresses":     "公网IP"
  }[.|ascii_downcase] // .;
  sort_by(.type)[]
  | "  \(.type | zh)  |  \(.name)  (\(.location))"
'
echo ""

FROM="$(date -u +%Y-%m-01T00:00:00Z)"
if TO=$(date -u -v+1d +%Y-%m-%dT00:00:00Z 2>/dev/null); then :        # macOS
else TO=$(date -u -d "+1 day" +%Y-%m-%dT00:00:00Z); fi                 # Linux
BODY="$(mktemp)"; cat > "$BODY" <<EOF
{"type":"ActualCost","timeframe":"Custom","timePeriod":{"from":"$FROM","to":"$TO"},"dataset":{"granularity":"None","aggregation":{"totalCost":{"name":"Cost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"MeterCategory"}]}}
EOF

RESP=""
for attempt in 1 2; do
  if RESP=$(az rest --method post \
      --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
      --body @"$BODY" 2>&1); then break; fi
  if grep -q 429 <<<"$RESP" && [ "$attempt" = 1 ]; then
    echo "  (计费 API 限流,20 秒后重试一次…)"; sleep 20
  else echo "$RESP" >&2; exit 1; fi
done
rm -f "$BODY"

echo "══ ② 本月至今(与扣卡金额同源) ══"
jq -r --argjson budget "$BUDGET_USD" '
  . as $doc
  | ($doc.properties.columns | map(.name) | index("MeterCategory")) as $mi
  | ($doc.properties.rows | map(.[0]) | add // 0) as $t
  | "  花了: $\($t*100|round/100) / 预警线 \$\(budget)  (\(($t/$budget*100)|round)% 用掉)",
    "  \(([range(($t/$budget*20)|floor)] | map("█") | join("")))\([range(20-(($t/$budget*20)|floor))] | map("░") | join("")))",
    "  明细:",
    ($doc.properties.rows | sort_by(-.[0])[] | "      \(.[ $mi ]): $\(.[0]*100|round/100)")
' <<<"$RESP"
echo ""
echo "══ ③ 闸门 ══"
echo "  预算邮件告警: 未设(说一声就装,超 \$$BUDGET_USD/月 自动邮件)"
echo "  每周飞书播报: 未设(复用 keepalive 的 Actions+飞书 webhook)"
