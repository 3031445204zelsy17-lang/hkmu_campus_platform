# 官方 Advice Sheet 爬取与比对管线(2026-08-18)

数据源三层(全部公开):
1. 指南索引:`Advice_on_Course_Selection_Guide_3cru.pdf` → 57 个 3cr 计划码 + 入学年份适用规则
2. 每专业封面:`<码>_3cru_cover.pdf` → 内嵌各年级表链接 + 升 standing 门槛/层级学分约束
3. 每年级课表:`<子计划码>_Yr{1-4}.pdf` → **每份只含当前学期**(8 月发秋季版,春季版约 12 月,换季重爬)

产物在 `docs/ops/选课选课/advice_sheets/`:
- `covers/`(57 份)+ `yr/`(433 份)原始 PDF — **gitignore,不入库**
- `GE_catalog_3cru.pdf`(92 门官方 GE 目录,2026-08-07 版)+ `UG_elective_catalog_3cru.pdf`(477 门选修目录)
- `results/` 比对产物:`compare_result.json`(缺课/学分/年份全量比对)、`year_mismatch.json`(硬/软错位)等

脚本:
- `parse_yr.py` — 年级表 PDF → 结构化课行(已验证:商管 4/4、DSAI 5/5、全校 2498 行解析失败仅 12)
- `compare_all.py` — 官方 vs 我们的 PROGRAMMES/RULE_COURSE_CREDITS 全量比对(⚠️ 路径仍指向 /tmp,重跑前改脚本头部路径)
- `bulk_fetch.js` / `fetch2files.js` — Playwright 过 Cloudflare 批量抓取

## CF 过盾配方(血泪总结)

- curl 任何指纹 = 403;**无头 Playwright 也被识破**
- 可靠配方:有头 Chromium + `ignoreDefaultArgs:['--enable-automation']` + `--disable-blink-features=AutomationControlled`,过盾 15-30s
- 过盾后页面会跳转 → 必须再 goto 一次稳定,否则 evaluate 报 "Execution context destroyed"
- 取 PDF 用**页内 fetch**(同源同 TLS 同 cookie)→ base64 回传落盘;`ctx.request` API 走 Node TLS 会被 CF 拒
- 630KB 大文件页内超时给 ≥90s;官方对部分文件限速,并发无用
- 2 份官方真 404(截至 2026-08-18):BSSCHWSJ2-SCHJ2-ECON_Yr4、BSSCHWSJ3-SCHJ3-GCS_Yr4

## 结论速查(细节见 ~/Desktop/课程数据问题清单-2026-08-18.md)

学分 2498 行仅 1 门错;年份硬错 130/46 专业;缺课 76 课次(GIP 53 最重);GE 缺 19/92;选修目录 106 门全库没有;2 专业码缺失。

**教训:join 型管线对账必须双向(缺失+多余),覆盖率断言进 CI,否则漏收静默通过。**
