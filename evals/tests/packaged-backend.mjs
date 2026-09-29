import { mkdtemp, rm, readFile, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import assert from "node:assert/strict";
import { BackendProcess } from "../../apps/desktop/src/main/backend-process.ts";

const source = process.env.LIKETYPELESS_TEST_MODEL;
if (!source)
  throw new Error(
    "Set LIKETYPELESS_TEST_MODEL to an existing pinned model folder",
  );
const directory = await mkdtemp(join(tmpdir(), "liketypeless-独立后台 "));
const backend = new BackendProcess(
  resolve("dist/liketypeless-api/liketypeless-api.exe"),
  [],
  directory,
);
const manifest = (
  await readFile(resolve("evals/local/e2e-manifest.jsonl"), "utf8")
)
  .trim()
  .split(/\r?\n/)
  .map(JSON.parse);
const device = process.env.LIKETYPELESS_STT_DEVICE || "auto";
// No developer tools or CUDA directories from the host PATH may satisfy a missing bundle dependency.
process.env.PATH = join(process.env.SystemRoot, "System32");
const measurements = [];
try {
  await backend.start();
  await backend.request("/models/prepare", { sourcePath: source });
  for (let attempt = 0; attempt < 120; attempt++) {
    const status = await backend.request("/models/status");
    if (status.state === "error") throw new Error(status.error);
    if (status.state === "ready") break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  assert.equal((await backend.request("/health")).modelReady, true);
  const count = Number(process.env.LIKETYPELESS_TEST_TRANSCRIPTIONS || 3);
  for (let index = 0; index < count; index++) {
    const sample = manifest[index % manifest.length];
    const result = await backend.request("/stt/transcribe", {
      filePath: sample.audio_path,
    });
    assert.ok(result.text.trim());
    measurements.push({ id: sample.id, stt_ms: result.sttElapsedMs });
  }
  const health = await backend.request("/health");
  await mkdir(resolve("evals/local/product-validation"), { recursive: true });
  await writeFile(
    resolve("evals/local/product-validation/packaged-" + device + ".json"),
    JSON.stringify(
      {
        count,
        runtime: health.runtime,
        hostPathRestricted: true,
        microphoneUsed: false,
        measurements,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ count, runtime: health.runtime, passed: true }));
} finally {
  await backend.stop();
  await rm(directory, { recursive: true, force: true });
}
