import { accountRequestOptions, handleAccountResponse } from './auth';
import { reportDownloadUrl } from './scans';

// Same in-memory attachment ceiling and digest contract as the P4 Report V2
// reader. This verifies transport bytes, not license truth or publisher identity.
const MAX_BYTES = 32 * 1024 * 1024;
class InventoryDownloadError extends Error {}
const invalid = () => new InventoryDownloadError('资源清单附件完整性校验失败，未保存。');

export async function downloadResourceInventory(scanId: string, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  if (!scanId) throw invalid();
  let response: Response;
  try {
    response = await fetch(reportDownloadUrl(scanId, 'resource_inventory'), accountRequestOptions({
      method: 'GET', redirect: 'error', cache: 'no-store', signal,
      headers: { Accept: 'text/csv' },
    }));
  } catch {
    signal.throwIfAborted();
    throw new InventoryDownloadError('无法读取资源清单，请检查连接后手动重试。');
  }

  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let complete = false;
  try {
    signal.throwIfAborted();
    handleAccountResponse(response.status);
    if (response.status !== 200) throw new InventoryDownloadError(`资源清单下载失败（HTTP ${response.status}），未保存。`);
    if (response.redirected || response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'text/csv')
      throw new InventoryDownloadError('资源清单附件格式不匹配，未保存。');
    const digest = response.headers.get('Content-Digest');
    const etag = response.headers.get('ETag');
    if (!/^sha-256=:[A-Za-z0-9+/]{43}=:$/.test(digest ?? '') || !/^"sha256:[a-f0-9]{64}"$/.test(etag ?? ''))
      throw invalid();
    const declared = response.headers.get('Content-Length');
    if (declared !== null && (!/^[1-9]\d*$/.test(declared) || Number(declared) > MAX_BYTES))
      throw new InventoryDownloadError('资源清单附件为空或超过32MiB上限，未保存。');
    if (!response.body) throw invalid();
    reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) { complete = true; break; }
      size += value.byteLength;
      if (size > MAX_BYTES) throw new InventoryDownloadError('资源清单附件超过32MiB上限，未保存。');
      chunks.push(value);
    }
    if (!size || (declared !== null && Number(declared) !== size)) throw invalid();
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    signal.throwIfAborted();
    const hex = Array.from(hash, x => x.toString(16).padStart(2, '0')).join('');
    const base64 = btoa(Array.from(hash, x => String.fromCharCode(x)).join(''));
    if (etag !== `"sha256:${hex}"` || digest !== `sha-256=:${base64}:`) throw invalid();
    try { new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
    catch { throw new InventoryDownloadError('资源清单文字编码无效，未保存。'); }

    // No await between the final cancellation gate and the actual save action.
    signal.throwIfAborted();
    const url = URL.createObjectURL(new Blob([bytes], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    try {
      link.href = url;
      link.download = `${scanId.replace(/[^A-Za-z0-9_-]/g, '_')}-resources.csv`;
      document.body.append(link);
      link.click();
    } finally {
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  } catch (error) {
    signal.throwIfAborted();
    // Never expose arbitrary stream/network exception text or response bodies.
    if (error instanceof InventoryDownloadError) throw error;
    throw invalid();
  } finally {
    if (!complete) {
      if (reader) await reader.cancel().catch(() => {});
      else await response.body?.cancel().catch(() => {});
    }
    reader?.releaseLock();
  }
}
