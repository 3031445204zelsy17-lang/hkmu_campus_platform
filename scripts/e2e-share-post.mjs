// e2e-share-post.mjs — 帖子转发(分享)自动化验证
// 前置:
//   1. 本地后端已起 8765(配方见 memory local-pytest/automator)
//   2. miniprogram/utils/config.js API_BASE 临时指向 http://127.0.0.1:8765/api/v1
//   3. DevTools 已起自动端口:
//      /Applications/wechatwebdevtools.app/Contents/MacOS/cli auto \
//        --project <repo>/miniprogram --auto-port 9420
// 运行: node scripts/e2e-share-post.mjs
// 注:原生转发面板无法 automator 驱动,此处只断言 onShareAppMessage 返回值与 DOM;
//     面板观感(缩略图裁切/标题两行)靠开发者工具人眼复核。
import automator from "miniprogram-automator";
import assert from "node:assert/strict";

const WS = "ws://localhost:9420";
const IMAGE_POST_ID = 226; // 本地库带图测试帖(image_url 已由 psql 预置)
const TEXT_POST_ID = 225;  // 无图帖

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const mini = await automator.connect({ wsEndpoint: WS });

try {
  // --- 1) 带图帖:标题后缀 / path / imageUrl / 按钮渲染与文案 ---
  let page = await mini.reLaunch(`/pages/post-detail/post-detail?id=${IMAGE_POST_ID}`);
  await page.waitFor(".post-actions .share-action");
  await sleep(600); // 等 loadPost 完成后再断言返回值

  let share = await page.callMethod("onShareAppMessage");
  assert.ok(share.title.endsWith("· HKMU Campus"), `title 缺品牌后缀: ${share.title}`);
  assert.equal(share.path, `/pages/post-detail/post-detail?id=${IMAGE_POST_ID}`);
  assert.ok(share.imageUrl, "带图帖应有 imageUrl");

  const btn = await page.$(".post-actions .share-action");
  assert.ok(btn, "转发按钮未渲染");
  const label = await (await page.$(".share-action .post-action-count")).text();
  assert.equal(label, "转发", `按钮文案应为「转发」,实际: ${label}`);

  // --- 2) 语言切换 → 文案变 Share,标题后缀不变 ---
  await page.callMethod("handleLanguageChange", { detail: { locale: "en" } });
  await sleep(300);
  const labelEn = await (await page.$(".share-action .post-action-count")).text();
  assert.equal(labelEn, "Share", `切 en 后文案应为 Share,实际: ${labelEn}`);
  share = await page.callMethod("onShareAppMessage");
  assert.ok(share.title.endsWith("· HKMU Campus"), `en 下后缀应不变: ${share.title}`);

  // --- 3) 无图帖:返回值不含 imageUrl ---
  page = await mini.reLaunch(`/pages/post-detail/post-detail?id=${TEXT_POST_ID}`);
  await page.waitFor(".share-action");
  await sleep(600);
  share = await page.callMethod("onShareAppMessage");
  assert.ok(!("imageUrl" in share), `无图帖不应带 imageUrl: ${JSON.stringify(share)}`);
  assert.ok(share.title.endsWith("· HKMU Campus"));

  // --- 4) 死链:超大 id → notFound 空态(回归,非本次改动) ---
  page = await mini.reLaunch("/pages/post-detail/post-detail?id=99999999");
  await sleep(900);
  assert.ok(await page.$(".empty-state"), "死链应渲染 notFound 空态");

  console.log("ALL PASS ✅  (title/path/imageUrl/按钮/语言切换/无图/死链)");
} finally {
  await mini.disconnect();
}
