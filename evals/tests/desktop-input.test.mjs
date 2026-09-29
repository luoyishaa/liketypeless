import test from "node:test";
import assert from "node:assert/strict";
import { deliverText } from "../../apps/desktop/src/main/input-delivery.ts";

test("an unavailable target never changes the clipboard", async () => {
  let changed = false;
  const result = await deliverText("你好。", "target", {
    focus: async () => {
      throw new Error("目标窗口已关闭");
    },
    begin: async () => {
      changed = true;
      return "lease";
    },
    paste: async () => {},
    restore: async () => {},
  });
  assert.equal(result.status, "ready-to-copy");
  assert.equal(changed, false);
});

test("non-text clipboard is left untouched and the result remains available for copying", async () => {
  let pasted = false;
  const result = await deliverText("你好。", "target", {
    focus: async () => {},
    begin: async () => {
      throw new Error("剪贴板含图片");
    },
    paste: async () => {
      pasted = true;
    },
    restore: async () => {},
  });
  assert.equal(result.status, "ready-to-copy");
  assert.equal(pasted, false);
});

test("failed paste releases the clipboard lease without claiming success", async () => {
  let restored = false;
  const result = await deliverText("你好。", "target", {
    focus: async () => {},
    begin: async () => "lease",
    paste: async () => {
      throw new Error("焦点已改变");
    },
    restore: async () => {
      restored = true;
    },
  });
  assert.equal(restored, true);
  assert.equal(result.status, "ready-to-copy");
});

test("successful key submission is not reported as verified insertion", async () => {
  const result = await deliverText("你好。", "target", {
    focus: async () => {},
    begin: async () => "lease",
    paste: async () => {},
    restore: async () => {},
  });
  assert.equal(result.status, "paste-requested");
});
