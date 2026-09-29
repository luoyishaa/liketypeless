import { _electron as electron } from "playwright";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import assert from "node:assert/strict";

const directory = await mkdtemp(join(tmpdir(), "liketypeless-ui-"));
const screenshots = resolve("evals/local/desktop-smoke");
await mkdir(screenshots, { recursive: true });
const launchOptions = {
  args: [resolve("apps/desktop/out/main/index.js")],
  env: {
    ...process.env,
    LIKETYPELESS_TEST_DATA_DIR: directory,
    ELECTRON_RENDERER_URL: "",
  },
};
let instance = await electron.launch(launchOptions);
try {
  const page = await instance.firstWindow();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page
    .getByText("本机服务在线", { exact: true })
    .waitFor({ timeout: 45000 });
  await page.getByRole("heading", { name: "把想法变成文字" }).waitFor();
  await page.screenshot({
    path: join(screenshots, "home.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  await page.getByLabel("录音快捷键").fill("Ctrl+Shift+Space");
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.getByText("设置已保存。", { exact: true }).waitFor();
  await page.screenshot({
    path: join(screenshots, "settings.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "状态与帮助", exact: true }).click();
  await page.getByRole("button", { name: "重新启动服务", exact: true }).click();
  await page.getByText("服务已重新启动。", { exact: true }).waitFor();
  await page.evaluate(async () => {
    const settings = await window.liketypeless.settings();
    await window.liketypeless.updateSettings({
      ...settings,
      onboardingComplete: true,
    });
    await window.liketypeless.hideWindow();
  });
  assert.equal(
    await instance.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].isVisible(),
    ),
    false,
  );
  await instance.close();
  instance = await electron.launch(launchOptions);
  const reopened = await instance.firstWindow();
  await reopened
    .getByText("本机服务在线", { exact: true })
    .waitFor({ timeout: 45000 });
  assert.equal(
    await instance.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].isVisible(),
    ),
    false,
    "completed setup must launch into the tray",
  );
  await instance.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].show(),
  );
  assert.equal(
    await instance.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].isVisible(),
    ),
    true,
  );
  assert.deepEqual(errors, []);
  console.log(
    "Desktop smoke passed: backend, settings, restart and tray-first relaunch.",
  );
} finally {
  await instance.close();
  await rm(directory, { recursive: true, force: true });
}
