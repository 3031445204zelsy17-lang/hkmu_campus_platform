#!/usr/bin/env python3
# ═══ 点货脚本:期望清单(infra-manifest.yaml) vs 云上实况 ═══
# 用法:  python3 scripts/infra_audit.py
# 输出:  白话报告(对上/点名/成本);对不上 exit 1(CI/cron 可用作门禁)
# 时机:  每次要动云之前 + 每周例行
# 依赖:  az(已登录) + PyYAML;成本查询撞限流会优雅降级不算失败

import json
import subprocess
import sys
from datetime import date

try:
    import yaml
except ImportError:
    print("缺 PyYAML: pip3 install pyyaml"); sys.exit(2)

REPO = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
MANIFEST = yaml.safe_load(open(f"{REPO}/docs/ops/infra-manifest.yaml"))

problems = []


def az(*args, sub=None):
    cmd = ["az", *args]
    if sub:
        cmd += ["--subscription", sub]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout) if r.stdout.strip() else None


def sub_display(s):
    return f"{s['name']}({s['id'][:8]}…)"


print("══ ① 订阅对表 ══")
for s in MANIFEST["subscriptions"]:
    try:
        pol = az("account", "subscription", "show", "--id", s["id"]).get("subscriptionPolicies", {})
        quota = pol.get("quotaId", "?")
        state = az("account", "subscription", "show", "--id", s["id"]).get("state", "?")
    except Exception as e:
        problems.append(f"{s['name']}: 查不了订阅({e})"); print(f"  ❌ {sub_display(s)} 查不了: {e}"); continue
    ok_type = s["期望类型含"].lower() in quota.lower()
    print(f"  {'✅' if ok_type else '❌'} {sub_display(s)} 类型={quota} 状态={state}"
          + ("" if ok_type else f"  ← 期望含「{s['期望类型含']}」"))
    if not ok_type:
        problems.append(f"{s['name']}: 订阅类型变成 {quota}(期望含 {s['期望类型含']})")

print("\n══ ② 资源点货(多了少了都点名) ══")
expected = {(r["sub"][:8], r["type"].lower(), r["name"].lower()) for r in MANIFEST["resources"]}
optional = [{"type": p["type"].lower(), "name含": (p.get("name含") or "").lower()}
            for p in MANIFEST.get("可选_模式", [])]
for s in MANIFEST["subscriptions"]:
    live = az("resource", "list", "--output", "json", sub=s["id"])
    seen = set()
    print(f"  {sub_display(s)}: 实际 {len(live)} 个资源")
    for r in live:
        key = (s["id"][:8], r["type"].lower(), r["name"].lower())
        if key in expected:
            seen.add(key); print(f"    ✅ {r['name']}  ({r['type']})"); continue
        if any(o["type"] == r["type"].lower() and o["name含"] in r["name"].lower() for o in optional):
            print(f"    ⚪ {r['name']}  ({r['type']}) [可选,不违规]"); continue
        loc = f"({r.get('location')})" if r.get("location") else ""
        print(f"    ❌ {r['name']}  ({r['type']}) {loc}  ← 不在清单上!")
        problems.append(f"计划外资源: {r['name']} ({r['type']}) @ {s['name']}")
    for key in expected - seen:
        if key[0] == s["id"][:8]:
            print(f"    ❌ 清单里的 {key[2]} 不见了!")
            problems.append(f"清单资源缺失: {key[2]} @ {s['name']}")

print("\n══ ③ 本月成本 vs 上限 ══")
ceiling = MANIFEST["_meta"]["月成本上限_usd"]
from_d = date.today().replace(day=1).strftime("%Y-%m-01T00:00:00Z")
to_d = f"{date.today().strftime('%Y-%m-%d')}T23:59:59Z"
body = json.dumps({"type": "ActualCost", "timeframe": "Custom",
                   "timePeriod": {"from": from_d, "to": to_d},
                   "dataset": {"granularity": "None",
                               "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}}}})
total, queried = 0.0, []
for s in MANIFEST["subscriptions"]:
    r = subprocess.run(["az", "rest", "--method", "post",
                        "--url", f"https://management.azure.com/subscriptions/{s['id']}/providers/Microsoft.CostManagement/query?api-version=2023-11-01",
                        "--body", body], capture_output=True, text=True)
    try:
        rows = json.loads(r.stdout)["properties"]["rows"]
        c = sum(x[0] for x in rows) if rows else 0.0
        total += c; queried.append(f"{s['name']}=${c:.2f}")
    except Exception:
        print(f"  ⚠️ {s['name']} 成本查询被限流/失败,跳过(不算对不上)")
if queried:
    bar = "█" * min(20, int(total / ceiling * 20)) + "░" * max(0, 20 - int(total / ceiling * 20))
    print(f"  本月至今: ${total:.2f} / 上限 ${ceiling}  {' '.join(queried)}")
    print(f"  {bar}")
    if total > ceiling:
        problems.append(f"本月成本 ${total:.2f} 超上限 ${ceiling}")

print("\n" + ("═" * 44))
if problems:
    print(f"❌ 点货不合格,{len(problems)} 处对不上:")
    for p in problems:
        print(f"   • {p}")
    sys.exit(1)
print("✅ 点货合格:清单与实况一致,成本在限内")
