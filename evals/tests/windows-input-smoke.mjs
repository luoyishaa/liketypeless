import { _electron as electron } from "playwright";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import {
  deliverToWindow,
  getForegroundWindowHandle,
} from "../../apps/desktop/src/main/windows-input.ts";

const instance = await electron.launch({
  args: [resolve("evals/tests/windows-input-target.cjs")],
});
try {
  const page = await instance.firstWindow();
  await page.getByRole("textbox", { name: "测试输入框" }).focus();
  const target = await instance.evaluate(({ BrowserWindow }) => {
    const window = BrowserWindow.getAllWindows()[0];
    return `${window.getNativeWindowHandle().readBigUInt64LE()}:${process.pid}`;
  });
  await instance.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].focus(),
  );
  const foreground = await getForegroundWindowHandle();
  console.log(JSON.stringify({ target, foreground }));
  const prior = await instance.evaluate(({ clipboard }) =>
    clipboard.readText(),
  );
  const formats = await instance.evaluate(async ({ clipboard }) =>
    (await clipboard.read()).flatMap((item) => item.types),
  );
  const text = "你好，语音输入测试。";
  const started = performance.now();
  if (foreground !== target) {
    await assert.rejects(deliverToWindow(target, text), /录音后切换了窗口/);
    assert.equal(
      await instance.evaluate(({ clipboard }) => clipboard.readText()),
      prior,
    );
    console.log(
      "Native input protection passed: another window is foreground; paste path not exercised.",
    );
  } else {
    let protectedClipboard = false;
    try {
      await deliverToWindow(target, text);
    } catch (error) {
      if (String(error).includes("剪贴板含图片或其他格式")) {
        protectedClipboard = true;
      } else {
        throw error;
      }
    }
    if (protectedClipboard) {
      assert.deepEqual(
        await instance.evaluate(async ({ clipboard }) =>
          (await clipboard.read()).flatMap((item) => item.types),
        ),
        formats,
      );
      assert.equal(
        await instance.evaluate(({ clipboard }) => clipboard.readText()),
        prior,
      );
      console.log(
        "Native input protection passed: non-text clipboard unchanged; paste path not exercised.",
      );
    } else {
      await page
        .getByRole("textbox", { name: "测试输入框" })
        .inputValue()
        .then((value) => assert.equal(value, text));
      assert.equal(
        await instance.evaluate(({ clipboard }) => clipboard.readText()),
        prior,
        "Clipboard text must be restored",
      );
      console.log(
        JSON.stringify({
          nativeDeliveryMs: Math.round(performance.now() - started),
          typedIntoOwnedWindow: true,
          clipboardRestored: true,
        }),
      );
    }
  }
} finally {
  await instance.close();
}
