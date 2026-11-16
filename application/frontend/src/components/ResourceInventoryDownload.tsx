import { useLayoutEffect, useRef } from 'react';
import { DownloadControl } from './ui';
import { downloadResourceInventory } from '../services/resourceInventory';

// Selective adaptation of xzb's resource download wiring (dae821df76c7).
// Resources keys this component by Scan ID; the shared control keeps its lock,
// busy/error feedback and explicit retry. No report or business state is cached.
export function ResourceInventoryDownload({ scanId }: { scanId: string }) {
  const active = useRef<AbortController | null>(null);
  useLayoutEffect(() => () => {
    active.current?.abort();
    active.current = null;
  }, [scanId]);

  async function start() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    try {
      await downloadResourceInventory(scanId, controller.signal);
    } finally {
      if (active.current === controller) active.current = null;
    }
  }

  return <DownloadControl onDownload={start}>下载完整资源清单</DownloadControl>;
}
