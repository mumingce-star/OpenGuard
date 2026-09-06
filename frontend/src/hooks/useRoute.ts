import { useEffect, useState } from "react";
import type { Mode } from "../types/domain";
import { defaultMode } from "../services/scans";
export type Page =
  | "overview"
  | "new-scan"
  | "progress"
  | "risks"
  | "resources"
  | "report"
  | "not-found"
  | "home";
export function readRoute() {
  const { pathname, search } = window.location;
  const query = new URLSearchParams(search);
  const mode: Mode =
    query.get("mode") === "api"
      ? "api"
      : query.get("mode") === "mock"
        ? "mock"
        : defaultMode;
  if (pathname === "/")
    return { page: "home" as Page, scanId: "", riskId: "", query, mode };
  if (pathname === "/app/new-scan")
    return { page: "new-scan" as Page, scanId: "", riskId: "", query, mode };
  const m = pathname.match(
    /^\/app\/scans\/([^/]+)\/(overview|progress|risks|resources|report)(?:\/([^/]+))?\/?$/,
  );
  if (m && (!m[3] || m[2] === "risks")) {
    try {
      return {
        page: m[2] as Page,
        scanId: decodeURIComponent(m[1]),
        riskId: m[3] ? decodeURIComponent(m[3]) : "",
        query,
        mode,
      };
    } catch {
      /* Invalid URL */
    }
  }
  // Legacy taskless routes never load an arbitrary previous demo.
  const legacy =
    /^\/app\/(overview|progress|risk|risks|resources|report)\/?$/.test(
      pathname,
    );
  return {
    page: legacy ? ("new-scan" as Page) : ("not-found" as Page),
    scanId: "",
    riskId: "",
    query,
    mode,
  };
}
export function scanPath(
  id: string,
  page: Page,
  mode: Mode,
  query?: URLSearchParams,
  riskId?: string,
) {
  const p = new URLSearchParams(query);
  p.set("mode", mode);
  return (
    "/app/scans/" +
    encodeURIComponent(id) +
    "/" +
    page +
    (riskId ? "/" + encodeURIComponent(riskId) : "") +
    "?" +
    p
  );
}
export function useRoute() {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    window.history.scrollRestoration = "manual";
    const pop = () => {
      setRoute(readRoute());
      requestAnimationFrame(() =>
        window.scrollTo(0, Number(history.state?.scroll ?? 0)),
      );
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  function go(url: string, restore = false) {
    try {
      sessionStorage.setItem(
        "og-scroll:" + location.pathname + location.search,
        String(window.scrollY),
      );
    } catch {
      /* best effort */
    }
    history.replaceState({ ...history.state, scroll: window.scrollY }, "");
    history.pushState({}, "", url);
    setRoute(readRoute());
    let y = 0;
    if (restore)
      try {
        y = Number(
          sessionStorage.getItem(
            "og-scroll:" + location.pathname + location.search,
          ) ?? 0,
        );
      } catch {
        /* best effort */
      }
    requestAnimationFrame(() => window.scrollTo(0, y));
  }
  function filter(name: string, value: string) {
    const q = new URLSearchParams(location.search);
    value ? q.set(name, value) : q.delete(name);
    history.replaceState(history.state, "", location.pathname + "?" + q);
    setRoute(readRoute());
  }
  return { route, go, filter };
}
