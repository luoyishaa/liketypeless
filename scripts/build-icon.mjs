// Deterministic Windows ICO rendering of resources/icon.svg; no browser or network.
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const size = 256;
const stride = size * 4;
const maskStride = Math.ceil(size / 32) * 4;
const dib = Buffer.alloc(40 + stride * size + maskStride * size);
dib.writeUInt32LE(40, 0);
dib.writeInt32LE(size, 4);
dib.writeInt32LE(size * 2, 8);
dib.writeUInt16LE(1, 12);
dib.writeUInt16LE(32, 14);
dib.writeUInt32LE(stride * size, 20);
const rounded = (x, y, left, top, right, bottom, radius) => {
  const cx = Math.max(left + radius, Math.min(x, right - radius));
  const cy = Math.max(top + radius, Math.min(y, bottom - radius));
  return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2;
};
for (let y = 0; y < size; y++)
  for (let x = 0; x < size; x++) {
    let red = 0,
      green = 0,
      blue = 0,
      alpha = 0;
    for (let sy = 0; sy < 4; sy++)
      for (let sx = 0; sx < 4; sx++) {
        const px = x + (sx + 0.5) / 4,
          py = y + (sy + 0.5) / 4;
        if (!rounded(px, py, 0, 0, 256, 256, 64)) continue;
        const arc = Math.hypot(px - 128, py - 130);
        const mic =
          rounded(px, py, 101, 45, 155, 151, 27) ||
          (py >= 130 && arc >= 44.5 && arc <= 57.5) ||
          rounded(px, py, 70.5, 109.5, 83.5, 136.5, 6.5) ||
          rounded(px, py, 172.5, 109.5, 185.5, 136.5, 6.5) ||
          rounded(px, py, 121.5, 174.5, 134.5, 215.5, 6.5) ||
          rounded(px, py, 96.5, 202.5, 159.5, 215.5, 6.5);
        red += mic ? 245 : 35;
        green += mic ? 249 : 92;
        blue += mic ? 241 : 75;
        alpha++;
      }
    const offset = 40 + ((size - 1 - y) * size + x) * 4;
    if (alpha) {
      dib[offset] = Math.round(blue / alpha);
      dib[offset + 1] = Math.round(green / alpha);
      dib[offset + 2] = Math.round(red / alpha);
      dib[offset + 3] = Math.round((alpha / 16) * 255);
    } else
      dib[
        40 + stride * size + (size - 1 - y) * maskStride + Math.floor(x / 8)
      ] |= 128 >> x % 8;
  }
const header = Buffer.alloc(22);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(1, 4);
header.writeUInt16LE(1, 10);
header.writeUInt16LE(32, 12);
header.writeUInt32LE(dib.length, 14);
header.writeUInt32LE(22, 18);
await writeFile(
  resolve("apps/desktop/resources/icon.ico"),
  Buffer.concat([header, dib]),
);
console.log("Built Windows application icon from the microphone geometry.");
