# 视觉设计文档 · HKMU 背书汇报 PPT

## 1. Profile 基线声明
- 选用:`profiles/strategic.md`(向决策者争取资源/背书的提案场景,与「向主任争取官方背书」最匹配)
- 参考维度:克制商务风、每页一个核心论点、大数字卡片、优先级条形、路线图
- 偏离说明:用户明确要求「深蓝主色 + 浅蓝/白底 + 少量绿色点缀(平台视觉蓝绿系)」,颜色以用户要求优先;不使用图片插画,全程几何+排版驱动(学校汇报场合,克制优先,且提示词要求架构图自绘、不要截图)

## 2. 风格基线
- 锚点:瑞士国际主义排版 + 咨询报告式克制网格;大留白、细分割线、直角矩形
- 参考其网格纪律与字级对比,不参考其配色

## 3. 风格细则
- 色彩:主色深蓝 #163B6E(标题/大数字/封面底),深海军蓝 #0E2A50(渐变深处),浅蓝 #E9F1FA(卡片底),点缀绿 #1FA383(对勾/强调/关键条),页面白底,浅灰蓝底 #F6F9FD,正文 #22314A,辅助 #5D6F88,分割线 #D9E3EF
- 字体:全篇 MiSans(中西文统一,屏幕汇报友好);封面题 60px / 页标题 30px bold / 大数字 52px bold / 正文 15-18px / 注释 12-14px
- 容器:直角矩形卡片,无边框或 2px 主色边框;禁用圆角与阴影堆砌;绿色仅用于对勾、重点标签、关键条
- 图形:P7 用简单水平条形(shape 绘制);P8 方块图 shape+连线自绘;无照片、无图标堆砌,图标仅小号实心 FontAwesome 辅助

## 4. 版式系统
- 页边距 72px;内容页统一:kicker(13px 绿,加宽字距)@ y44 → 页标题 30px bold @ y70 → 绿色短条 64×4 @ y126 → 正文区 y170-640 → 页脚(左:项目名,右:页码)@ y682
- 封面/结尾:深蓝满版 + 低透明同心圆装饰 + 白色大标题 + 绿色短条
- 目录页:编号列表式,一问一行;数据页:四等宽大数字卡;优先级页:递减宽度条形;架构页:横向流程方块图

## 5. 样式使用规则
- pageTitle:内容页标题;kicker:栏目眉;body:正文;small:注释/页脚
- primary:标题、大数字、深色卡片、封面底;accent:仅对勾、强调标签、标题下短条、关键条形;blueSoft/bgSoft:卡片底

## 6. 风险禁令
- 禁止出现密钥/服务器地址/IP/域名;禁止内部策略内容;禁止历史故障;数字只准用提示词清单
- 正文字号 ≥15px(注释 ≥12px);单行文本必须 wrap:false;左右分栏底边对齐
- 禁止把 310 说成「数百活跃用户」;承诺一律用「恳请/愿意配合」语气

## 7. Theme 定义
```yaml
theme:
  colors:
    primary: "#163B6E"
    primaryDeep: "#0E2A50"
    blueSoft: "#E9F1FA"
    accent: "#1FA383"
    bgSoft: "#F6F9FD"
    text: "#22314A"
    secondary: "#5D6F88"
    line: "#D9E3EF"
  textStyles:
    pageTitle: {fontSize: 30, color: "$primary", fontFamily: "MiSans"}
    kicker: {fontSize: 13, color: "$accent", fontFamily: "MiSans", letterSpacing: 3}
    body: {fontSize: 18, color: "$text", fontFamily: "MiSans", lineHeight: 1.55}
    small: {fontSize: 13, color: "$secondary", fontFamily: "MiSans", lineHeight: 1.4}
```
