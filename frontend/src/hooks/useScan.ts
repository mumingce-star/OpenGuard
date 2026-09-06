import { useCallback, useEffect, useState } from "react";
import type { Mode, Scan } from "../types/domain";
import { getScan } from "../services/scans";
import { usePageVisibility } from "./usePageVisibility";
export function useScan(id: string, mode: Mode) {
  const [state, setState] = useState<{
    key: string;
    scan: Scan | null;
    error: string | null;
    loading: boolean;
  }>({ key: "", scan: null, error: null, loading: false });
  const [revision, setRevision] = useState(0);
  const visible = usePageVisibility();
  const reload = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    if (!id) return;
    const ctrl = new AbortController();
    let timer: number | undefined;
    const key = mode + ":" + id;
    setState((previous) =>
      previous.key === key && previous.scan
        ? { ...previous, error: null, loading: false }
        : { key, scan: null, error: null, loading: true },
    );
    async function load() {
      try {
        const scan = await getScan(id, mode, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setState({ key, scan, error: null, loading: false });
        if (visible && ["queued", "running"].includes(scan.status))
          timer = window.setTimeout(load, mode === "mock" ? 500 : 2500);
      } catch (e) {
        if (!ctrl.signal.aborted)
          setState({
            key,
            scan: null,
            error: e instanceof Error ? e.message : "读取任务失败",
            loading: false,
          });
      }
    }
    void load();
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [id, mode, revision, visible]);
  const current = state.key === mode + ":" + id;
  return {
    scan: current ? state.scan : null,
    error: current ? state.error : null,
    loading: !!id && (!current || state.loading),
    reload,
  };
}
