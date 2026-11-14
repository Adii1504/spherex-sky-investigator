// Reproducible, obviously synthetic calibration PNGs. No astronomical imagery.
import { mkdirSync, writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const destination = fileURLToPath(new URL('../public/fixtures/', import.meta.url));
mkdirSync(destination, { recursive: true });
const glyphs = {
  D: ['11110','10001','10001','10001','10001','10001','11110'],
  E: ['11111','10000','10000','11110','10000','10000','11111'],
  M: ['10001','11011','10101','10101','10001','10001','10001'],
  O: ['01110','10001','10001','10001','10001','10001','01110'],
  1: ['00100','01100','00100','00100','00100','00100','01110'],
  2: ['01110','10001','00001','00010','00100','01000','11111'],
  3: ['11110','00001','00001','01110','00001','00001','11110'],
};
function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const name = Buffer.from(type);
  const size = Buffer.alloc(4); size.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([name, data])));
  return Buffer.concat([size, name, data, crc]);
}
for (let frame = 1; frame <= 3; frame++) {
  const size = 512;
  const pixels = Buffer.alloc(size * size * 3);
  const paint = (x, y, color) => { if (x >= 0 && x < size && y >= 0 && y < size) pixels.set(color, (y * size + x) * 3); };
  const box = (x, y, w, h, color) => { for (let dy = y; dy < y + h; dy++) for (let dx = x; dx < x + w; dx++) paint(dx, dy, color); };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const gray = (Math.floor(x / 64) + Math.floor(y / 64)) % 2 ? 21 : 29;
    paint(x, y, [gray, gray, gray]);
  }
  for (let p = 0; p < size; p += 64) { box(p, 0, 1, size, [70, 70, 70]); box(0, p, size, 1, [70, 70, 70]); }
  box(40, 100 + frame * 30, 432, 12, [72, 199, 208]);
  box(65 + frame * 80, 160, 12, 220, [227, 189, 57]);
  const text = (value, x, y, scale, color) => {
    for (const letter of value) {
      glyphs[letter].forEach((row, j) => [...row].forEach((bit, i) => { if (bit === '1') box(x + i * scale, y + j * scale, scale, scale, color); }));
      x += scale * 6;
    }
  };
  box(35, 25, 440, 64, [5, 5, 5]); text('DEMO', 48, 32, 7, [227, 189, 57]);
  text(String(frame), 342, 263, 13, [230, 230, 230]);
  text('DEMO', 48, 440, 6, [72, 199, 208]);
  const raw = Buffer.alloc((size * 3 + 1) * size);
  for (let y = 0; y < size; y++) pixels.copy(raw, y * (size * 3 + 1) + 1, y * size * 3, (y + 1) * size * 3);
  const header = Buffer.alloc(13); header.writeUInt32BE(size); header.writeUInt32BE(size, 4); header[8] = 8; header[9] = 2;
  writeFileSync(`${destination}/demo-frame-${frame}.png`, Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk('IHDR', header), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}
console.log('Generated three labelled development calibration charts.');
