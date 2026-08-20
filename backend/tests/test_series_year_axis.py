"""批次 5 双系列 cohort 轴:per-(专业, 入学点) 年份映射(验收标准批次 5)。

语义(官方佐证,420/420 份 advice sheet 页眉核对):plan 码尾数字 N =
「Year N Entry」入学点 —— Y2/Y3 入学(advanced standing)与 Y1 入学是同年
不同路径,官方各自出 advice sheet;同一门课在不同入学点路径下的官方修读年
可以不同(BEDHACLSJ 系列 2 的 UNI2002BCW 在 Y3,系列 1 在 Y2 —— 批次 2
验收遗留②)。本批建模:

  PROGRAMME_ENTRY_SERIES   {专业: {系列: {"entry_level", "label"}}}
  SERIES_YEAR_OVERRIDES    {专业: {系列: {课: {"year","term"}}}}(≠ 默认图的差分)
  users.entry_level        1/2/3(PUT /users/me,onboarding 采集)
  graduation-status        返回按 entry_level 过滤的 placements + series 标签

数据侧锁:SERIES_YEAR_OVERRIDES 必须与「my_rows.json 按生成器同口径重算」
全等(重算逻辑直接 import 生成器,不做二手复刻);labels 因 CI 无 poppler
不参与重算,以已知字面量锚定。
"""
import importlib.util
import re
from pathlib import Path

import pytest

from backend.app.data.programme_year_map import (
    PROGRAMME_ENTRY_SERIES, PROGRAMME_YEAR_MAP, SERIES_YEAR_OVERRIDES,
)
from backend.app.data.programmes import PROGRAMMES, PROGRAMME_ALIASES

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "docs/ops/选课选课/advice_sheets/verify"


def _generator():
    """importlib 加载生成器(只借它的纯计算函数,不触发 main/写文件)。"""
    spec = importlib.util.spec_from_file_location(
        "build_programme_year_map_under_test",
        REPO / "scripts" / "build_programme_year_map.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _recompute():
    """my_rows.json + 提交在库的默认图 → 重算系列轴(labels 置空)。"""
    gen = _generator()
    import json
    rows = json.loads((VERIFY / "my_rows.json").read_text(encoding="utf-8"))
    return gen.build_series_axes(
        rows, PROGRAMMES, PROGRAMME_YEAR_MAP, {}, PROGRAMME_ALIASES)


def test_series_overrides_match_recompute():
    """系列差分 ≡ 生成器口径重算(防手改/防上游 my_rows 变了没重生成)。"""
    meta, overrides = _recompute()
    got_levels = {p: {s: m["entry_level"] for s, m in v.items()}
                  for p, v in meta.items()}
    want_levels = {p: {s: m["entry_level"] for s, m in v.items()}
                   for p, v in PROGRAMME_ENTRY_SERIES.items()}
    assert got_levels == want_levels, (
        f"PROGRAMME_ENTRY_SERIES 与重算不符:"
        f"多 {sorted(set(got_levels) - set(want_levels))} / "
        f"少 {sorted(set(want_levels) - set(got_levels))} / "
        f"值异 { {k for k in set(got_levels) & set(want_levels) if got_levels[k] != want_levels[k]} };"
        "对账:python3 scripts/build_programme_year_map.py 重生成"
    )
    assert overrides == SERIES_YEAR_OVERRIDES, (
        f"SERIES_YEAR_OVERRIDES 与重算不符:"
        f"多 {sorted(set(overrides) - set(SERIES_YEAR_OVERRIDES))} / "
        f"少 {sorted(set(SERIES_YEAR_OVERRIDES) - set(overrides))};"
        f"课次级差异见 diff;对账:重跑生成器"
    )
    # 差分键必须都在默认图里(override 不能凭空造 placement)
    for p, by_series in SERIES_YEAR_OVERRIDES.items():
        for cid in (c for diff in by_series.values() for c in diff):
            assert cid in PROGRAMME_YEAR_MAP[p], (
                f"{p}/{cid} 差分引用了默认图没有的课 —— 生成器保证 diff ⊆ default"
            )


def test_series_metadata_labels():
    """系列元数据:entry_level=系列数字;label 是官方页眉口径(锚定字面量)。"""
    assert PROGRAMME_ENTRY_SERIES["BEDHACLSJ"]["2"] == {
        "entry_level": 2, "label": "2026/27 Year 2 Entry"}
    assert set(PROGRAMME_ENTRY_SERIES["BAHCAMDJ"]) == {"1", "2", "3"}
    pat = re.compile(r"20\d{2}/\d{2} Year [123] Entry")
    bad = [
        (p, s, m["label"])
        for p, v in PROGRAMME_ENTRY_SERIES.items()
        for s, m in v.items()
        if m["entry_level"] != int(s) or not pat.fullmatch(m["label"])
    ]
    assert not bad, f"系列元数据形状不对(须 entry_level=系列数字+页眉标签):{bad[:5]}"


def test_placements_series_axis_known_cases():
    """行为锁:已知跨系列年份分歧案例(BEDHACLSJ/BAHCAMDJ/BAHELCJ)。"""
    from backend.app.routers.courses import _placements_for

    # 案例①(批次 2 遗留②):BEDHACLSJ 系列 2 的 UNI2002BCW 官方 Y3,默认 Y2
    default = _placements_for("BEDHACLSJ")[0]
    assert default["UNI2002BCW"]["year"] == 2, "默认图(系列 1 口径)应为 Y2"
    s2 = _placements_for("BEDHACLSJ", entry_level=2)[0]
    assert s2["UNI2002BCW"]["year"] == 3, "Y2 入学者的官方 advice 在 Y3 修"
    assert s2["CHIN2253ECF"]["year"] == 2  # 同差分组另一门
    # entry_level=1 = 默认口径,不该有差分(BEDHACLSJ 只有系列 2 差分)
    assert _placements_for("BEDHACLSJ", entry_level=1)[0]["UNI2002BCW"]["year"] == 2
    # 缺失 entry_level → 默认图(宁少判不误判)
    assert _placements_for("BEDHACLSJ", entry_level=None)[0] == default

    # 案例②:BAHCAMDJ 系列 3 的 3000 级创作课推到 Y4(默认 Y2)
    assert _placements_for("BAHCAMDJ")[0]["CCA3000ACF"]["year"] == 2
    assert _placements_for("BAHCAMDJ", entry_level=3)[0]["CCA3000ACF"]["year"] == 4
    assert _placements_for("BAHCAMDJ", entry_level=2)[0]["UNI1002ABW"]["year"] == 3

    # 案例③(系列 1 也有差分):BAHELCJ 默认图取系列 2 的 C 行(LANG3138AEF
    # Y4,非 E 口径),系列 1 自己的 E 行在 Y3
    assert _placements_for("BAHELCJ")[0]["LANG3138AEF"]["year"] == 4
    assert _placements_for("BAHELCJ", entry_level=1)[0]["LANG3138AEF"]["year"] == 3

    # WSJ Stream 限定码回退伞码(批次 4 语义不回归)+ 系列差分照常生效
    assert _placements_for("BSSCHWSJ-AGS")[0], "Stream 限定码应有伞码映射"
    # 未知专业 → 空(前端回退 courses 表)
    assert _placements_for("NOSUCHPROG") == ({}, [])

    # 不污染模块级默认图(entry_level 视图必须是拷贝)
    assert PROGRAMME_YEAR_MAP["BEDHACLSJ"]["UNI2002BCW"]["year"] == 2


async def test_graduation_status_series_placements(client, make_user):
    """端到端:PUT 入学点 → graduation-status 返回系列化 placements + 标签。"""
    import uuid
    _uid, token = await make_user(f"series_axis_{uuid.uuid4().hex[:8]}")
    hdr = {"Authorization": f"Bearer {token}"}

    # 未填入学点:placements = 默认图,series = None
    r = await client.put(
        "/api/v1/users/me", headers=hdr, json={"programme_code": "BEDHACLSJ"})
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/courses/graduation-status", headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["placements"]["UNI2002BCW"]["year"] == 2
    assert body["series"] is None

    # 填 Y2 入学点:UNI2002BCW → Y3 + 官方系列标签
    r = await client.put(
        "/api/v1/users/me", headers=hdr, json={"entry_level": 2})
    assert r.status_code == 200, r.text
    assert r.json()["entry_level"] == 2
    r = await client.get("/api/v1/courses/graduation-status", headers=hdr)
    body = r.json()
    assert body["placements"]["UNI2002BCW"]["year"] == 3, (
        f"Y2 入学者应见 Y3,实得 {body['placements']['UNI2002BCW']}"
    )
    assert body["series"] == {"entry_level": 2, "label": "2026/27 Year 2 Entry"}

    # 值域外拒绝(1/2/3 之外 400,不静默落库)
    r = await client.put(
        "/api/v1/users/me", headers=hdr, json={"entry_level": 5})
    assert r.status_code == 400, r.text


async def test_programmes_expose_series_metadata(client):
    """/programmes 携带系列元数据(onboarding 采入学点的数据源)。"""
    r = await client.get("/api/v1/courses/programmes")
    assert r.status_code == 200
    progs = {p["code"]: p for p in r.json()["programmes"]}
    assert set(progs["BEDHACLSJ"]["series"]) == {"1", "2"}
    assert progs["BEDHACLSJ"]["series"]["2"]["label"] == "2026/27 Year 2 Entry"
