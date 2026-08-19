"""UG 选修目录(UG_elective_catalog_3cru.pdf)独立重数:双引擎 × 双锚点。

背景:旧结论 477/106/205 三个数是单方脚本结果(验收标准.md 批次0 标 ⚠️ 未复核)。
本脚本按 GE 目录同款纪律重数:
  引擎  pdftotext(poppler -layout) / pypdf
  锚点  A=TOC 行(码行,本行或折行下一行尾带页码;点线渲染 0~n 个,不可靠)
        B=正文条目(条目作用域绑定:Credit-units:/學分: 必须落在本码行与下一码行之间)
  幻影码防线:Prerequisites/Excluded 值折行后行首带码的引用抢不到标签(作用域绑定),
  TOC 锚点要求非正文行,天然不采值行。
  收敛标准:两引擎按同锚点必须完全一致;两锚点差集须为空或逐码说明(TOC 官方漏行)。

产出:verify/elec_catalog.json(码集+计数+锚点差集)、verify/elec_coverage.json
  (选修池长尾 = 规则 elective 课 − 目录;not_in_plannable/not_in_whole_db 两口径)。
用法:python3 docs/ops/选课选课/advice_sheets/verify/elec_catalog_check.py
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDF = HERE.parent / "UG_elective_catalog_3cru.pdf"
REPO = Path(__file__).resolve().parents[5]   # .../hkmu-campus-platform

CODE = re.compile(r'^([A-Z]{2,5})\s+(\d{3,4}[A-Z]{3})\s+\S')   # 行首码+标题
# 行尾页码(点线可有可无)。(?<![A-Za-z]) 挡住 "; J1" 这类行尾标识(字母紧贴数字)。
PAGE_TAIL = re.compile(r'(?<![A-Za-z])\d{1,3}\s*$')
LABEL = re.compile(r'\bCredit-units\s*:|學分')                 # 条目标签(英/中)


def get_text(engine: str) -> str:
    if engine == "poppler":
        return subprocess.run(
            ["pdftotext", "-layout", str(PDF), "-"],
            capture_output=True, text=True, check=True).stdout
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(PDF)).pages)


def extract(engine: str) -> dict:
    lines = get_text(engine).split("\n")
    code_lines = [(i, m.group(1) + m.group(2))
                  for i, raw in enumerate(lines)
                  if (m := CODE.match(raw.strip()))]
    body, toc = [], []
    for k, (i, code) in enumerate(code_lines):
        nxt = code_lines[k + 1][0] if k + 1 < len(code_lines) else len(lines)
        scope_has_label = any(LABEL.search(x) for x in lines[i + 1:nxt])
        if scope_has_label:                                       # 锚点B:正文条目
            body.append(code)
            continue
        # 锚点A:目录行。页码最多折到下一行;再远会跨条目误采(pypdf 无版面更敏感)。
        if any(PAGE_TAIL.search(x.strip()) for x in lines[i:min(nxt, i + 2)]):
            toc.append(code)
    return {"toc": sorted(set(toc)), "toc_rows": len(toc),
            "body": sorted(set(body)), "body_rows": len(body)}


def naive_count() -> int:
    """朴素全文正则去重(无锚点)——旧 477 的取数方式,用于佐证幻影多计。"""
    text = subprocess.run(["pdftotext", "-layout", str(PDF), "-"],
                          capture_output=True, text=True, check=True).stdout
    return len(set(re.findall(r'\b[A-Z]{2,5}\s+\d{3,4}[A-Z]{3}\b', text)))


def main() -> None:
    res = {e: extract(e) for e in ("poppler", "pypdf")}
    for e, r in res.items():
        print(f"[{e}] TOC {r['toc_rows']}行/去重{len(r['toc'])} | 正文 {r['body_rows']}行/去重{len(r['body'])}")
    eng_ok = (res["poppler"]["toc"] == res["pypdf"]["toc"]
              and res["poppler"]["body"] == res["pypdf"]["body"])
    print(f"引擎间一致: {eng_ok}")

    body_set, toc_set = set(res["poppler"]["body"]), set(res["poppler"]["toc"])
    anchor_extra = sorted(body_set - toc_set)      # 有正文条目但 TOC 没行
    anchor_miss = sorted(toc_set - body_set)       # 有 TOC 行但无正文条目(幻影嫌疑)
    print(f"锚点差集: 正文−TOC {anchor_extra} | TOC−正文 {anchor_miss}")
    catalog = sorted(body_set)
    print(f"朴素全文正则去重 = {naive_count()}(对照:条目锚 {len(catalog)})")

    # ── 我们侧(静态课源,不连 DB;生产表由同源灌注) ──
    sys.path.insert(0, str(REPO / "backend"))
    from app.data.ge_courses import GE_COURSES
    from app.data.programme_rules import PROGRAMME_RULES

    plannable = {c["code"].replace(" ", "") for c in GE_COURSES}   # courses 表宇宙的静态代理
    elec_pool = set()
    for p, e in PROGRAMME_RULES.items():
        for cat, v in e["categories"].items():
            for cid in v.get("courses", []):
                plannable.add(cid)
                if cat == "elective":               # 选修池=elective 类目(pool='credits')
                    elec_pool.add(cid)
    _tree = ast.parse((REPO / "scripts/seed_courses.py").read_text())
    for node in _tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "COURSES":
            for c in ast.literal_eval(node.value):
                plannable.add(c["id"])
    catalogue = set()                                # 只读 catalogue 表(skill.md 3cru 部分)
    for ln in (REPO / "docs/ops/选课选课/skill.md").read_text(encoding="utf-8").splitlines():
        m = re.search(r'\[代码:\s*([A-Z]{2,5})\s+(\d{4}[A-Z]{3})\]', ln)
        if m:
            catalogue.add(m.group(1) + m.group(2))
    whole_db = plannable | catalogue

    cat_set = set(catalog)
    longtail = sorted(elec_pool - cat_set)
    not_in_plannable = sorted(cat_set - plannable)
    not_in_whole_db = sorted(cat_set - whole_db)
    print(f"\n选修目录(重数) {len(catalog)}")
    print(f"规则选修池 {len(elec_pool)} | 长尾(池−目录) {len(longtail)}")
    print(f"目录−可规划宇宙({len(plannable)}) = {len(not_in_plannable)}")
    print(f"目录−全库(再并 skill.md 3cru {len(catalogue)}) = {len(not_in_whole_db)}")

    json.dump({"poppler_toc": res["poppler"]["toc"], "poppler_body": res["poppler"]["body"],
               "pypdf_toc": res["pypdf"]["toc"], "pypdf_body": res["pypdf"]["body"],
               "engines_agree": eng_ok,
               "body_minus_toc_official_toc_omissions": anchor_extra,
               "toc_minus_body": anchor_miss,
               "naive_fulltext_dedupe": naive_count()},
              open(HERE / "elec_catalog.json", "w"), ensure_ascii=False, indent=1)
    json.dump({"catalog_n": len(catalog), "elec_pool_n": len(elec_pool),
               "longtail_n": len(longtail), "longtail": longtail,
               "not_in_plannable_n": len(not_in_plannable), "not_in_plannable": not_in_plannable,
               "not_in_whole_db_n": len(not_in_whole_db), "not_in_whole_db": not_in_whole_db},
              open(HERE / "elec_coverage.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n→ {HERE / 'elec_catalog.json'} / {HERE / 'elec_coverage.json'}")


if __name__ == "__main__":
    main()
