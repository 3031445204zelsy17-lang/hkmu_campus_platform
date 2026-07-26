// CI: validate every miniprogram file the WeChat toolchain depends on.
//   - every .json parses (a malformed app.json / page.json / project config
//     breaks the miniprogram build, but the backend CI never touches it)
//   - every .js has valid syntax (otherwise surfaces only inside WeChat
//     devtools, not at PR time)
// Run locally:  node scripts/check_miniprogram.mjs
// Run in CI:    .github/workflows/quality.yml → miniprogram job
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = "miniprogram";

function walk(dir) {
  let out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out = out.concat(walk(p));
    else out.push(p);
  }
  return out;
}

let bad = 0;
for (const f of walk(ROOT)) {
  if (f.endsWith(".json")) {
    try {
      JSON.parse(readFileSync(f, "utf8"));
    } catch (e) {
      console.error(`JSON ✗ ${f}: ${e.message}`);
      bad++;
    }
  } else if (f.endsWith(".js")) {
    // node --check parses without executing, so the missing wx/Page/App globals
    // don't matter — it only catches syntax errors.
    try {
      execFileSync("node", ["--check", f], { stdio: "pipe" });
    } catch (e) {
      const detail = (e.stderr && e.stderr.toString()) || e.message;
      console.error(`JS ✗ ${f}\n${detail}`);
      bad++;
    }
  }
}

if (bad) {
  console.error(`\n${bad} miniprogram file(s) failed.`);
  process.exit(1);
}
console.log("miniprogram JSON + JS syntax OK");
