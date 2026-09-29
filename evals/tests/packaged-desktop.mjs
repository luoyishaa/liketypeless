import { _electron as electron } from "playwright";
import { resolve } from "node:path";
import assert from "node:assert/strict";

// This smoke test prepares the real application's user profile for manual acceptance.
const restarts = Number(process.env.LIKETYPELESS_TEST_APP_RESTARTS || 1);
for (let index = 0; index < restarts; index++) {
  const instance = await electron.launch({
    executablePath: resolve(
      "apps/desktop/release/win-unpacked/liketypeless.exe",
    ),
    args: [],
    env: { ...process.env, LIKETYPELESS_TEST_DATA_DIR: "hide-window-only" },
  });
  try {
    const page = await instance.firstWindow();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page
      .getByText("本机服务在线", { exact: true })
      .waitFor({ timeout: 60000 });
    assert.equal(await instance.evaluate(({ app }) => app.isPackaged), true);
    // Existing models are re-verified asynchronously at startup; do not race that
    // state by trying to import while the button is legitimately disabled.
    let modelStatus;
    for (let attempt = 0; attempt < 120; attempt++) {
      modelStatus = await page.evaluate(() =>
        window.liketypeless.modelStatus(),
      );
      if (!["verifying", "downloading"].includes(modelStatus.state)) break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    assert.ok(
      !["verifying", "downloading"].includes(modelStatus.state),
      "Model verification timed out",
    );
    const source = process.env.LIKETYPELESS_TEST_MODEL;
    if (source && modelStatus.state !== "ready") {
      // Mock only the native directory picker; model import and verification are real.
      await instance.evaluate(({ dialog }, source) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [source],
        });
      }, source);
      await page
        .getByRole("button", { name: "导入已有模型", exact: true })
        .click();
      await page
        .getByRole("button", { name: "在这里试录", exact: true })
        .waitFor();
      for (let attempt = 0; attempt < 120; attempt++) {
        if (
          (await page.evaluate(() => window.liketypeless.health())).modelReady
        )
          break;
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
    assert.equal(
      (await page.evaluate(() => window.liketypeless.health())).modelReady,
      true,
    );
    await page.getByRole("heading", { name: "把想法变成文字" }).waitFor();
    assert.deepEqual(errors, []);
    console.log(
      `Packaged application cycle ${index + 1}/${restarts} passed startup and pinned model availability.`,
    );
  } finally {
    await instance.close();
  }
}
