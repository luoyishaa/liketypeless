import test from "node:test";
import assert from "node:assert/strict";
import { deliverText } from "../../apps/desktop/src/main/input-delivery.ts";
import { deliverToWindow } from "../../apps/desktop/src/main/windows-input.ts";

test("without a target the saved result stays available without touching Windows", async () => {
  let called = false;
  const result = await deliverText("你好。", null, {
    deliver: async () => {
      called = true;
    },
  });
  assert.equal(result.status, "ready-to-copy");
  assert.equal(called, false);
});

test("native failure keeps the result available for manual copy", async () => {
  const result = await deliverText("你好。", "target", {
    deliver: async () => {
      throw new Error("焦点已改变，文字已保留");
    },
  });
  assert.equal(result.status, "ready-to-copy");
  assert.match(result.reason, /焦点已改变/);
});

test("native completion means key submission, not verified insertion", async () => {
  const result = await deliverText("你好。", "target", {
    deliver: async () => {},
  });
  assert.equal(result.status, "paste-requested");
});

test("invalid target never invokes a native clipboard transaction", async () => {
  await assert.rejects(
    deliverToWindow("not-a-window", "你好。"),
    /无效的目标窗口/,
  );
});
