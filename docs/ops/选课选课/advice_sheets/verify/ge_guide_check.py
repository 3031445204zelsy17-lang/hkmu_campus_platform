r"""GE Selection Guide(GE_selection_guide_3cru.pdf)本学年开课集 canonical 提取。

产出 verify/ge_offered.json = 三轮(2026秋/2027春/2027暑)各轮开课码集。

为什么不用 pypdf 做第二引擎:复核报告第二节已证 pypdf 对「GEN 前缀与课号拆行」
的行丢文本(1011ABF/1012ACF/2003ABF/1027ACF/1026ACF/1144ECF);本脚本仍跑 pypdf
做对照并记录差集,若 pypdf 修好了折行,差集应为空。

锚点与幻影防线:
  * 学期表分节 = "NNNN <Term> Term:" 到下一个 "Remarks:"(含 2045ECF 这类
    Remarks 互斥引用码,只出现在备注里,不是开课行——复核报告已人眼判定);
  * 行内取 `\b\d{4}[A-Z]{3}\b` 课号 token,不要求 GEN 前缀同行(1144ECF 的
    GEN 被折到下一行,逐行配前缀的解析器必丢它)。

交叉校验(复核报告人眼结论,数字已双验,本脚本只做机械化收敛核对):
  秋 33 / 春 34 / 暑 11 = 78 行次,跨轮重复 5,去重 73;春表含 1144ECF、
  不含 2045ECF;与池(GE_COURSES)集合相等(报告「意外收敛」)。
用法:python3 docs/ops/选课选课/advice_sheets/verify/ge_guide_check.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDF = HERE.parent / "GE_selection_guide_3cru.pdf"
REPO = Path(__file__).resolve().parents[5]

TERM_HEAD = re.compile(r'^(20\d{2}) (Autumn|Spring|Summer) Term:\s*$')
TOKEN = re.compile(r'\b(\d{4}[A-Z]{3})\b')


def get_text(engine: str) -> str:
    if engine == "poppler":
        return subprocess.run(["pdftotext", "-layout", str(PDF), "-"],
                              capture_output=True, text=True, check=True).stdout
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(PDF)).pages)


def extract_terms(engine: str) -> dict:
    lines = get_text(engine).split("\n")
    terms, cur = {}, None
    for raw in lines:
        l = raw.strip()
        m = TERM_HEAD.match(l)
        if m:
            cur = f"{m.group(1)} {m.group(2)}"
            terms[cur] = []
            continue
        if l.startswith("Remarks:"):        # 备注区(互斥引用码的老窝)到此为止
            cur = None
            continue
        if cur is not None:
            terms[cur].extend(TOKEN.findall(l))
    return {k: sorted(set("GEN" + t for t in v)) for k, v in terms.items()}


def main() -> None:
    po, py = extract_terms("poppler"), extract_terms("pypdf")
    print("[poppler]", {k: len(v) for k, v in po.items()})
    print("[pypdf]  ", {k: len(v) for k, v in py.items()})

    # 复核报告人眼基准(2026-08-19,双验过,勿改)
    EXPECT = {"2026 Autumn": 33, "2027 Spring": 34, "2027 Summer": 11}
    EXPECT_DUPS = {"GEN1042ECF", "GEN1050EBF", "GEN1060EBF", "GEN2044EBF", "GEN2255ECF"}
    assert set(po) == set(EXPECT), f"轮次异常: {sorted(po)}"

    all_tokens = [c for v in po.values() for c in v]
    dups = {c for c in all_tokens if all_tokens.count(c) > 1}
    offered = sorted(set(all_tokens))
    checks = {
        "per_term_counts_match_report": all(len(po[k]) == n for k, n in EXPECT.items()),
        "unique_73": len(offered) == 73,
        "row_sum_78": len(all_tokens) == sum(EXPECT.values()),
        "dups_are_the_5_known": dups == EXPECT_DUPS,
        "spring_has_1144_split_line_row": "GEN1144ECF" in po["2027 Spring"],
        "2045ECF_absent_remarks_only": "GEN2045ECF" not in offered,
        "pypdf_token_parity": po == py,
    }
    for k, v in checks.items():
        print(("✓" if v else "✗"), k)

    # 与官方目录(双引擎三锚收敛的 89)和池的关系
    ge_sets = json.load(open(HERE / "ge_sets.json"))
    official = set(ge_sets["toc"])
    sys.path.insert(0, str(REPO / "backend"))
    from app.data.ge_courses import GE_COURSES
    pool = {c["code"].replace(" ", "") for c in GE_COURSES}
    # 池 terms vs 指南轮次:跨轮课按轮次全集聚合;复核报告已知 2 门元数据错(1012ACF/2013SEF 应 spring)
    guide_terms = {}
    for k, v in po.items():
        t = k.split()[1].lower()
        for c in v:
            guide_terms.setdefault(c, set()).add(t)
    mismatch = {}
    for c in GE_COURSES:
        cid = c["code"].replace(" ", "")
        if cid in guide_terms and set(c["terms"]) != guide_terms[cid]:
            mismatch[cid] = {"pool_terms": c["terms"], "guide": sorted(guide_terms[cid])}
    checks["pool_equals_offered"] = pool == set(offered)
    checks["offered_subset_of_catalog89"] = set(offered) <= official
    checks["terms_mismatch_only_known_2"] = set(mismatch) == {"GEN1012ACF", "GEN2013SEF"}
    print(("✓" if checks["pool_equals_offered"] else "✗"), "pool_equals_offered")
    print(("✓" if checks["offered_subset_of_catalog89"] else "✗"), "offered ⊆ 目录89")
    print(("✓" if checks["terms_mismatch_only_known_2"] else "✗"),
          f"terms 元数据错仅已知2门: {mismatch}")

    json.dump({"poppler": po, "pypdf": py, "all": offered,
               "checks": checks, "terms_mismatch": mismatch},
              open(HERE / "ge_offered.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n→ {HERE / 'ge_offered.json'}")


if __name__ == "__main__":
    main()
