// UI classification only. Backend archive safety and scan coverage remain authoritative.
// Read bounded ZIP directory metadata; do not decompress or execute any member.
export async function isOpenGuardEvaluationPackage(file: File): Promise<boolean> {
  const tail = new Uint8Array(await file.slice(Math.max(0, file.size - 65557)).arrayBuffer());
  const view = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
  for (let at = tail.length - 22; at >= 0; at--) {
    if (view.getUint32(at, true) !== 0x06054b50) continue;
    if (at + 22 + view.getUint16(at + 20, true) !== tail.length) continue;
    if (view.getUint16(at + 4, true) !== 0 || view.getUint16(at + 6, true) !== 0) return false;
    const count = view.getUint16(at + 10, true);
    const size = view.getUint32(at + 12, true), offset = view.getUint32(at + 16, true);
    if (count !== view.getUint16(at + 8, true) || count > 512 || size > 262144 || offset + size > file.size - tail.length + at) return false;
    const bytes = new Uint8Array(await file.slice(offset, offset + size).arrayBuffer());
    const directory = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const names = new Set<string>();
    let cursor = 0;
    for (let index = 0; index < count; index++) {
      if (cursor + 46 > bytes.length || directory.getUint32(cursor, true) !== 0x02014b50) return false;
      const length = directory.getUint16(cursor + 28, true);
      const next = cursor + 46 + length + directory.getUint16(cursor + 30, true) + directory.getUint16(cursor + 32, true);
      if (next > bytes.length) return false;
      // Only exact ASCII root names are relevant to our own export format.
      const rawName = bytes.subarray(cursor + 46, cursor + 46 + length);
      if (rawName.length <= 128 && rawName.every(byte => byte >= 32 && byte <= 126)) names.add(String.fromCharCode(...rawName));
      cursor = next;
    }
    if (cursor !== bytes.length) return false;
    return ['VERSION_BINDING.json', 'FILE_HASHES.json', 'START_HERE.html', '02_P2/Result.json', '01_REPORT/Assessment.json'].every(name => names.has(name))
      && !['package.json', 'pyproject.toml', 'requirements.txt', 'pom.xml', 'Cargo.toml', 'go.mod'].some(name => names.has(name));
  }
  return false;
}

export function selectedZipSize(file: Pick<File, 'size'>): string {
  return `${file.size.toLocaleString('en-US')} 字节（${(file.size / 1024).toFixed(2)} KiB）`;
}

export const evaluationPackageMessage = '检测到 OpenGuard 评估结果包结构。它保存的是报告、Result 和材料，不是待扫描的源码项目。请重新选择原始项目 ZIP；演示输入为 is-number-7.0.0-derived.zip（4,172 字节）。';
