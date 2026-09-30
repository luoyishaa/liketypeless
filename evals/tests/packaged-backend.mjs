import { mkdtemp, rm, readFile, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import assert from "node:assert/strict";
import { BackendProcess } from "../../apps/desktop/src/main/backend-process.ts";

const source = process.env.LIKETYPELESS_TEST_MODEL;
const shortSource = process.env.LIKETYPELESS_TEST_SHORT_MODEL;
const downloadShort = process.env.LIKETYPELESS_TEST_SHORT_DOWNLOAD === "1";
if (shortSource && downloadShort)
  throw new Error("Choose import or official short-model download, not both");
const testShort = Boolean(shortSource || downloadShort);
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
  await readFile(resolve(testShort
    ? "evals/local/holdout-short-aishell1-official-v2.jsonl"
    : "evals/local/e2e-manifest.jsonl"), "utf8")
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
  if (testShort) {
    await backend.request("/models/short/prepare", shortSource ? { sourcePath: shortSource } : {});
    for (let attempt = 0; attempt < (downloadShort ? 1200 : 120); attempt++) {
      const status = await backend.request("/models/short/status");
      if (status.state === "error") throw new Error(status.error);
      if (status.state === "ready") break;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    assert.equal((await backend.request("/models/short/status")).state, "ready");
  }
  const count = Number(process.env.LIKETYPELESS_TEST_TRANSCRIPTIONS || 3);
  const audioOverride = process.env.LIKETYPELESS_TEST_AUDIO_OVERRIDE;
  for (let index = 0; index < count; index++) {
    const sample = manifest[index % manifest.length];
    const result = await backend.request("/stt/transcribe", {
      filePath: index === 0 && audioOverride ? audioOverride : sample.audio_path,
    });
    assert.ok(result.text.trim());
    if (testShort && sample.duration_seconds <= 4) {
      assert.equal(result.provider, "local-sensevoice-gguf", JSON.stringify(result));
      assert.equal(result.sttFallbackReason, null);
    }
    measurements.push({ id: sample.id, stt_ms: result.sttElapsedMs,
      provider: result.provider, fallbackReason: result.sttFallbackReason });
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
        alternateAudioUsed: Boolean(audioOverride),
        shortModelImported: Boolean(shortSource),
        shortModelDownloaded: downloadShort,
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
