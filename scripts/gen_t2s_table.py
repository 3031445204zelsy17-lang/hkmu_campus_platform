"""Regenerate miniprogram/utils/search.js (CJK 繁→简单字对照 + searchFold).

小程序端搜索归一化的对照表来源:遍历 BMP CJK 区段(扩展A/基本区/兼容区),
逐字过 OpenCC t2s,收录「单字→单字且发生变化」的映射(当前 3751 对,~23KB)。
多字输出(罕见)与恒等字(简繁同形,如 算/理/士)不收录。

再生成:
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/gen_t2s_table.py
写入文件后对照表部分不可手改——改 searchFold 逻辑请直接改本脚本内模板再重跑。
"""

import sys

from opencc import OpenCC  # 仅 3.13 Frameworks python 装了 opencc

OUT = "miniprogram/utils/search.js"

TEMPLATE = '''// 搜索文本归一化(小程序端零依赖):繁→简 + 全角→半角 + 小写 + 空白折叠。
// 目的:让「数据/數據」「ＤＡＴＡ/data」在专业/GE 搜索里互相命中。
// 对照表由 backend OpenCC(t2s) 全量 BMP 单字生成,勿手改——
// 重生成:python3 scripts/gen_t2s_table.py(见脚本头注释)。
const T = "{T}";
const S = "{S}";

// 按位对应(BMP 单字=1 个 UTF-16 码元),加载时建 Map 一次
const T2S = new Map();
for (let i = 0; i < T.length; i++) T2S.set(T[i], S[i]);

// 繁→简(逐字,BMP 表意区外原样保留)
function t2s(str) {
  return String(str || "").replace(/[\\u3400-\\u4DBF\\u4E00-\\u9FFF\\uF900-\\uFAFF]/g, (ch) => T2S.get(ch) || ch);
}

// 搜索折叠:查询词与匹配串两侧都用它,折叠后做子串匹配即可简繁/全角互通。
// 空白整体删除而非折叠:课码「GEN 1022AEF」与输入「gen1022」/全角「ＧＥＮ１０２２」互通
function searchFold(str) {
  if (!str) return "";
  return t2s(String(str))
    .replace(/[\\uFF01-\\uFF5E]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)) // 全角→半角
    .toLowerCase()
    .replace(/\\s+/g, "");
}

module.exports = { t2s, searchFold };
'''


def main() -> None:
    cc = OpenCC("t2s")
    pairs = []
    # 输出侧必须同为 BMP:个别简体形落在 CJK 扩展B(astral,JS 里 2 码元)会令
    # JS 按位配对错位(实测「數」→「帱」),且这类字用户根本打不出来,直接弃收
    for lo, hi in [(0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)]:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            out = cc.convert(ch)
            if out != ch and len(out) == 1 and ord(out) <= 0xFFFF:
                pairs.append((ch, out))

    t = "".join(p[0] for p in pairs)
    s = "".join(p[1] for p in pairs)
    # 防御:双串按位等长且全 BMP(JS 按码元配对的前提),否则按位配对会错位
    assert len(t) == len(s)
    assert all(ord(c) <= 0xFFFF for c in t + s)

    content = TEMPLATE.replace("{T}", t).replace("{S}", s)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK {len(pairs)} pairs -> {OUT} ({len(content.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    sys.exit(main())
