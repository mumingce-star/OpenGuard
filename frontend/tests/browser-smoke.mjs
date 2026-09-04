import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createRequire } from "node:module";
import { runtime } from "./runtime.mjs";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.OPENGUARD_PLAYWRIGHT || "playwright");
const base = process.env.OPENGUARD_TEST_URL || "http://127.0.0.1:5174";
const output =
  process.env.OPENGUARD_QA_OUTPUT ||
  path.join(os.tmpdir(), "openguard-frontend-qa");
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({
  channel: process.env.OPENGUARD_BROWSER || "chrome",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  reducedMotion: "reduce",
  acceptDownloads: true,
});
const page = await context.newPage(),
  errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const { createSnapshot } = runtime().load("mocks/data.ts");
let count = 0;
async function check(name, fn) {
  await fn();
  console.log("PASS " + ++count + " " + name);
}
async function visible(text) {
  await page.getByText(text, { exact: true }).first().waitFor();
}
async function seed(scenario = "standard", id = "DEMO-QA") {
  const scan = createSnapshot(id, scenario);
  await page.evaluate(
    ({ scan, scenario }) =>
      localStorage.setItem(
        "openguard:scan:v2:" + scan.id,
        JSON.stringify({
          scan,
          scenario,
          start: Date.now() - 12000,
          skip: true,
        }),
      ),
    { scan, scenario },
  );
  return id;
}
const taskUrl = (id, section, query = "") =>
  base +
  "/app/scans/" +
  id +
  "/" +
  section +
  "?mode=mock" +
  (query ? "&" + query : "");
async function downloadText(button) {
  const promise = page.waitForEvent("download");
  await button.click();
  const d = await promise;
  return fs.readFile(await d.path(), "utf8");
}
async function noOverflow() {
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
    "viewport has horizontal overflow",
  );
}
try {
  await page.goto(base + "/app/new-scan?mode=mock");
  await check("explicit new task and input validation", async () => {
    await page
      .getByRole("button", { name: "校验输入并播放演示", exact: true })
      .click();
    await visible("请输入 GitHub 仓库地址。");
    await page.getByLabel("公开仓库地址").fill("https://evil.example/a/b");
    await page
      .getByRole("button", { name: "校验输入并播放演示", exact: true })
      .click();
    await page
      .getByRole("alert")
      .filter({ hasText: "请输入 https://github.com" })
      .waitFor();
    await page.getByRole("button", { name: "上传 ZIP", exact: true }).click();
    await page.locator("input[type=file]").setInputFiles({
      name: "bad.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("x"),
    });
    await visible("仅支持 .zip 文件；安全检查和解压由后端执行。");
    await page.locator("input[type=file]").setInputFiles({
      name: "example.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK demo"),
    });
    await visible("example.zip");
    await page.getByRole("button", { name: "移除文件", exact: true }).click();
    await visible("拖放 ZIP 文件到这里");
  });
  await check("demo creation, skip and same ID after refresh", async () => {
    await page
      .getByRole("button", { name: "载入固定演示", exact: true })
      .click();
    await page.getByRole("heading", { name: "任务等待中" }).waitFor();
    const url = page.url();
    await page.getByRole("button", { name: "跳过等待", exact: true }).click();
    await page
      .getByRole("heading", { name: "扫描已完成", exact: true })
      .waitFor();
    await page.reload();
    await page
      .getByRole("heading", { name: "扫描已完成", exact: true })
      .waitFor();
    assert.equal(page.url(), url);
  });
  const id = await seed();
  await check(
    "metrics navigate to matching full-snapshot filters",
    async () => {
      await page.goto(taskUrl(id, "overview"));
      await page
        .locator(".og-metric")
        .filter({ hasText: "待处理风险" })
        .click();
      await page.getByRole("heading", { name: "筛选结果 · 3 / 4" }).waitFor();
      assert.ok(page.url().includes("handling=pending"));
    },
  );
  await check(
    "risk identity, query persistence, detail refresh and handling independence",
    async () => {
      await page.getByLabel("严重度", { exact: true }).selectOption("high");
      await page.getByLabel("资源类型", { exact: true }).selectOption("Model");
      await page.getByRole("heading", { name: "筛选结果 · 1 / 4" }).waitFor();
      await page.getByRole("button", { name: /模型许可证字段缺失/ }).click();
      assert.ok(page.url().includes("/risks/RISK-002"));
      await page
        .getByLabel("证据原文")
        .filter({ hasText: "DemoResearch-8B" })
        .waitFor();
      await page.reload();
      await page
        .getByRole("heading", { name: "模型许可证字段缺失", exact: true })
        .waitFor();
      await page
        .getByLabel("处理状态", { exact: true })
        .selectOption("resolved");
      await visible("处理状态已保存；复扫验证状态没有改变。");
      await visible("验证状态：未复扫验证");
      await page
        .getByRole("button", { name: "← 返回风险列表（保留筛选）" })
        .click();
      assert.equal(
        await page.getByLabel("资源类型", { exact: true }).inputValue(),
        "Model",
      );
      await page.getByRole("heading", { name: "筛选结果 · 0 / 4" }).waitFor();
    },
  );
  await check(
    "different risk evidence, absent original text and safe clipboard failure",
    async () => {
      await page.goto(taskUrl(id, "risks/RISK-001"));
      await page
        .getByLabel("证据原文")
        .filter({ hasText: "transformers==4.52.0" })
        .waitFor();
      await page.getByRole("button", { name: "许可原文", exact: true }).click();
      await visible("原文待补充");
      await page.getByRole("button", { name: "判断依据", exact: true }).click();
      await page
        .getByLabel("证据原文")
        .filter({ hasText: "尚未核实上游 NOTICE" })
        .waitFor();
      await page.evaluate(() =>
        Object.defineProperty(navigator, "clipboard", {
          configurable: true,
          value: { writeText: () => Promise.reject(new Error("denied")) },
        }),
      );
      await page.getByRole("button", { name: "复制建议", exact: true }).click();
      await page.getByRole("alert").filter({ hasText: "复制失败" }).waitFor();
      await page.getByRole("button", { name: "关闭提示", exact: true }).click();
    },
  );
  await check(
    "resource filters, bounded CSV and dialog keyboard focus restoration",
    async () => {
      await page.goto(taskUrl(id, "resources"));
      await page.getByLabel("类型", { exact: true }).selectOption("Model");
      await page.getByLabel("仅许可待确认").check();
      const csv = await downloadText(
        page.getByRole("button", {
          name: "导出筛选结果 CSV（1）",
          exact: true,
        }),
      );
      assert.equal(csv.split("\r\n").length, 2);
      assert.ok(csv.includes("DemoResearch"));
      assert.ok(!csv.includes("transformers"));
      const row = page.locator(".og-resource-row").first();
      await row.click();
      await page.getByRole("dialog").waitFor();
      await page.keyboard.press("Escape");
      await page.getByRole("dialog").waitFor({ state: "hidden" });
      assert.ok(await row.evaluate((e) => e === document.activeElement));
    },
  );
  await check(
    "graph lazy-load, focus filter, keyboard node reader and reset",
    async () => {
      await page.goto(taskUrl(id, "graph", "focus=RISK-002"));
      await page
        .getByRole("heading", { name: "证据关系图谱", exact: true })
        .waitFor();
      const nodeButton = page
        .getByLabel("节点证据快捷入口")
        .getByRole("button", { name: /ev-3/ });
      await nodeButton.focus();
      await page.keyboard.press("Enter");
      await page.getByRole("dialog").waitFor();
      await page
        .getByRole("dialog")
        .getByLabel("证据原文")
        .filter({ hasText: "DemoResearch" })
        .waitFor();
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: "重置视图", exact: true }).click();
      await page.getByLabel("当前风险").selectOption("RISK-001");
      assert.ok(page.url().includes("focus=RISK-001"));
    },
  );
  await check(
    "report has six actual chapters, same IDs and JSON counts",
    async () => {
      await page.goto(taskUrl(id, "report"));
      await page.getByRole("heading", { name: "06 / 证据附录" }).waitFor();
      assert.equal(await page.locator(".og-report section").count(), 6);
      const data = JSON.parse(
        await downloadText(
          page.getByRole("button", { name: "导出 JSON", exact: true }),
        ),
      );
      assert.equal(data.id, id);
      assert.equal(data.summary.resources, 7);
      assert.equal(data.summary.risks, 4);
      assert.equal(data.summary.pending, 2);
      await page.emulateMedia({ media: "print" });
      assert.equal(await page.locator(".og-sidebar").isVisible(), false);
      await page.screenshot({ path: path.join(output, "report-print.png") });
      await page.emulateMedia({ media: "screen" });
    },
  );
  await check(
    "empty, clean, missing, partial and failed scenario rendering",
    async () => {
      for (const [scenario, expected] of [
        ["clean", "本次未发现风险提示"],
        ["empty", "本次没有资源结果"],
      ]) {
        const id = await seed(scenario, "DEMO-" + scenario);
        await page.goto(taskUrl(id, "overview"));
        await visible(expected);
      }
      let id = await seed("missing", "DEMO-missing");
      await page.goto(taskUrl(id, "risks/RISK-001"));
      await visible("AI 解释 · 生成失败");
      await visible("证据待补充");
      for (const scenario of ["partial", "failed"]) {
        id = await seed(scenario, "DEMO-" + scenario);
        await page.goto(taskUrl(id, "progress"));
        await page
          .getByRole("heading", {
            name: scenario === "partial" ? "扫描部分完成" : "扫描失败",
            exact: true,
          })
          .waitFor();
        await page
          .getByRole("alert")
          .filter({ hasText: "任务未完整成功" })
          .waitFor();
      }
    },
  );
  await check(
    "invalid task/risk and API error are explicit without mock fallback",
    async () => {
      await page.goto(taskUrl("DEMO-absent", "overview"));
      await visible("无法读取当前任务");
      await page.goto(taskUrl("DEMO-QA", "risks/absent"));
      await visible("风险编号不存在");
      await page.route("http://localhost:8000/**", (r) =>
        r.fulfill({
          status: 404,
          contentType: "application/json",
          headers: { "Access-Control-Allow-Origin": "*" },
          body: "{}",
        }),
      );
      await page.goto(base + "/app/scans/REAL-404/overview?mode=api");
      await visible("无法读取当前任务");
      await visible("真实接口模式");
      assert.equal(await page.locator(".og-metric").count(), 0);
      await page.unroute("http://localhost:8000/**");
    },
  );
  await check(
    "intercepted API access check, duplicate-submit lock and GET-only refresh",
    async () => {
      let posts = 0,
        gets = 0,
        requestId = "";
      const scan = {
        ...createSnapshot("REAL-QA", "standard"),
        mode: "api",
        status: "completed",
        stageIndex: 7,
        finishedAt: new Date().toISOString(),
      };
      await page.route("http://localhost:8000/**", async (r) => {
        const req = r.request(),
          url = new URL(req.url()),
          headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
          };
        if (req.method() === "OPTIONS")
          return r.fulfill({ status: 204, headers });
        if (url.pathname === "/repositories/validate")
          return r.fulfill({ json: { accessible: true }, headers });
        if (url.pathname === "/scans" && req.method() === "POST") {
          posts++;
          requestId = req.headers()["idempotency-key"];
          await new Promise((done) => setTimeout(done, 250));
          return r.fulfill({ json: scan, headers });
        }
        gets++;
        return r.fulfill({ json: scan, headers });
      });
      await page.goto(base + "/app/new-scan?mode=api");
      await page
        .getByLabel("公开仓库地址")
        .fill("https://github.com/example/project");
      await page
        .getByRole("button", { name: "提交真实扫描", exact: true })
        .click();
      await visible("请先校验仓库访问状态。");
      await page
        .getByRole("button", { name: "校验仓库访问", exact: true })
        .click();
      await visible("后端已确认仓库可访问");
      await page
        .getByRole("button", { name: "提交真实扫描", exact: true })
        .evaluate((el) => {
          el.click();
          el.click();
        });
      await page
        .getByRole("heading", { name: "扫描已完成", exact: true })
        .waitFor();
      assert.equal(posts, 1);
      assert.ok(requestId);
      await page.reload();
      await page
        .getByRole("heading", { name: "扫描已完成", exact: true })
        .waitFor();
      assert.equal(posts, 1);
      assert.ok(gets >= 2);
      await page.unroute("http://localhost:8000/**");
    },
  );
  await check(
    "desktop, 1280x720 and 390px layouts, projection and reduced motion",
    async () => {
      await seed();
      for (const viewport of [
        { width: 1440, height: 900 },
        { width: 1280, height: 720 },
        { width: 390, height: 844 },
      ]) {
        await page.setViewportSize(viewport);
        for (const section of [
          "overview",
          "risks/RISK-001",
          "resources",
          "graph",
          "report",
        ]) {
          await page.goto(taskUrl("DEMO-QA", section));
          await page.locator(".og-page-header").waitFor();
          await noOverflow();
          if (
            section === "overview" ||
            section === "risks/RISK-001" ||
            section === "graph"
          )
            await page.screenshot({
              path: path.join(
                output,
                section.replaceAll("/", "-") + "-" + viewport.width + ".png",
              ),
            });
        }
        await page.goto(base + "/app/new-scan?mode=mock");
        await page.getByRole("heading", { name: "从一个项目开始" }).waitFor();
        await noOverflow();
      }
      await page.getByRole("button", { name: "打开导航", exact: true }).click();
      await page.getByRole("dialog").waitFor();
      await page.keyboard.press("Escape");
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto(taskUrl("DEMO-QA", "overview"));
      await page.getByRole("button", { name: "投屏模式", exact: true }).click();
      assert.equal(await page.locator(".og-sidebar").isVisible(), false);
      await noOverflow();
      await page.getByRole("button", { name: "退出投屏", exact: true }).click();
      await page.goto(base);
      await page
        .getByText("让每一个风险，都有证据可循；让每一次发布，都更有底气。", {
          exact: true,
        })
        .waitFor();
      await noOverflow();
      await page.screenshot({ path: path.join(output, "landing-1280.png") });
      const staticBefore = await page
        .locator(".particle-text")
        .evaluate((canvas) => canvas.toDataURL());
      await page.mouse.move(640, 280);
      await page.evaluate(
        () =>
          new Promise((done) =>
            requestAnimationFrame(() => requestAnimationFrame(done)),
          ),
      );
      const staticAfter = await page
        .locator(".particle-text")
        .evaluate((canvas) => canvas.toDataURL());
      assert.equal(
        staticAfter,
        staticBefore,
        "reduced-motion particles must stay static",
      );
      await page.setViewportSize({ width: 390, height: 844 });
      await noOverflow();
      await page.screenshot({ path: path.join(output, "landing-390.png") });
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.emulateMedia({ reducedMotion: "no-preference" });
      await page.mouse.move(300, 310);
      await page.mouse.move(900, 380, { steps: 15 });
      await page.screenshot({
        path: path.join(output, "landing-animated.png"),
      });
    },
  );
  assert.deepEqual(errors, []);
  console.log("PASS no uncaught browser errors");
  console.log(
    "RESULT " + count + " browser groups passed. Screenshots: " + output,
  );
} catch (error) {
  await page.screenshot({
    path: path.join(output, "failure.png"),
    fullPage: true,
  });
  console.error((await page.locator("body").innerText()).slice(0, 4000));
  throw error;
} finally {
  await browser.close();
}
