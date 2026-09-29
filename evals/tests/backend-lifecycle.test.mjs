import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { BackendProcess } from "../../apps/desktop/src/main/backend-process.ts";

test(
  "owned backend starts, serves authenticated basic mode and stops cleanly",
  { timeout: 180000 },
  async () => {
    const directory = await mkdtemp(join(tmpdir(), "liketypeless-启动 测试-"));
    const command =
      process.env.LIKETYPELESS_TEST_BACKEND ||
      resolve(".venv-release/Scripts/python.exe");
    const args = process.env.LIKETYPELESS_TEST_BACKEND
      ? []
      : [resolve("apps/local-api/scripts/serve_product.py")];
    const backend = new BackendProcess(command, args, directory);
    try {
      for (
        let index = 0;
        index < Number(process.env.LIKETYPELESS_TEST_RESTARTS || 2);
        index++
      ) {
        await backend.start();
        const health = await backend.request("/health");
        assert.equal(health.status, "ok");
        assert.equal(health.modelReady, false);
        const result = await backend.request("/llm/structure", {
          text: "明天开会",
          cleanupMode: "basic",
        });
        assert.equal(result.structuredText, "明天开会。");
        await backend.stop();
      }
    } finally {
      await backend.stop();
      await rm(directory, { recursive: true, force: true });
    }
  },
);
