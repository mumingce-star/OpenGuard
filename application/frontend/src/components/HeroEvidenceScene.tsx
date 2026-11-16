import { useEffect, useRef, useState } from "react";
import type { PointerEvent } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";

export function HeroEvidenceScene() {
  const sceneRef = useRef<HTMLElement>(null);
  const reducedMotion = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const [inView, setInView] = useState(true);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const onVisibility = () => setVisible(document.visibilityState === "visible");
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      threshold: 0.08,
    });
    observer.observe(scene);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const running = !reducedMotion && !paused && visible && inView;
  const tilt = (event: PointerEvent<HTMLElement>) => {
    if (event.pointerType !== "mouse" || !running) return;
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--glass-tilt-x", `${((0.5 - (event.clientY - rect.top) / rect.height) * 4).toFixed(2)}deg`);
    event.currentTarget.style.setProperty("--glass-tilt-y", `${(((event.clientX - rect.left) / rect.width - 0.5) * 6).toFixed(2)}deg`);
  };
  const resetTilt = () => {
    sceneRef.current?.style.removeProperty("--glass-tilt-x");
    sceneRef.current?.style.removeProperty("--glass-tilt-y");
  };
  useEffect(() => { if (reducedMotion) resetTilt(); }, [reducedMotion]);

  return (
    <figure
      ref={sceneRef}
      className="evidence-scene"
      data-running={running}
      onPointerMove={tilt}
      onPointerLeave={() => { if (running) resetTilt(); }}
      aria-label="溯源概念演示：来源线索穿过三层玻璃，形成证据与追溯连接，其中一条线索仍待核验"
    >
      <div className="evidence-scene-stage" aria-hidden="true">
        <div className="evidence-scene-halo" />
        <div className="evidence-scene-shadow" />
        <div className="evidence-pane evidence-pane-source">
          <svg viewBox="0 0 300 170" fill="none" preserveAspectRatio="none">
            <path className="evidence-refract" d="M20 118 C78 100 88 45 143 63 S229 104 282 36" />
            <path className="evidence-guide" d="M20 118 C78 100 88 45 143 63 S229 104 282 36" />
            <path className="evidence-path evidence-path-source" d="M20 118 C78 100 88 45 143 63 S229 104 282 36" />
            <path className="evidence-path evidence-path-source evidence-path-delayed" d="M19 55 C73 77 95 121 147 108 S227 68 280 124" />
            <g className="evidence-nodes"><circle cx="20" cy="118" r="5"/><circle cx="19" cy="55" r="4"/><circle cx="143" cy="63" r="5"/><circle cx="147" cy="108" r="4"/></g>
          </svg>
        </div>
        <div className="evidence-pane evidence-pane-middle">
          <svg viewBox="0 0 300 170" fill="none" preserveAspectRatio="none">
            <path className="evidence-refract" d="M20 92 C75 86 105 36 151 57 S223 111 280 76" />
            <path className="evidence-guide" d="M20 92 C75 86 105 36 151 57 S223 111 280 76" />
            <path className="evidence-path evidence-path-middle" d="M20 92 C75 86 105 36 151 57 S223 111 280 76" />
            <path className="evidence-path evidence-path-middle evidence-path-delayed" d="M18 127 C83 137 106 105 151 108 S219 50 282 44" />
            <g className="evidence-nodes"><circle cx="151" cy="57" r="5"/><circle cx="151" cy="108" r="4"/><circle cx="280" cy="76" r="5"/></g>
          </svg>
        </div>
        <div className="evidence-pane evidence-pane-front">
          <svg viewBox="0 0 300 170" fill="none" preserveAspectRatio="none">
            <path className="evidence-refract" d="M19 100 C83 100 94 48 148 67 S224 98 281 44" />
            <path className="evidence-guide" d="M19 100 C83 100 94 48 148 67 S224 98 281 44" />
            <path className="evidence-path evidence-path-front" d="M19 100 C83 100 94 48 148 67 S224 98 281 44" />
            <path className="evidence-path evidence-path-front evidence-path-delayed" d="M19 100 C81 93 103 130 151 111 S231 98 281 119" />
            <path className="evidence-path evidence-path-review" d="M151 111 C195 121 226 143 281 119" />
            <g className="evidence-nodes"><circle cx="19" cy="100" r="5"/><circle cx="148" cy="67" r="5"/><circle cx="151" cy="111" r="5"/><circle cx="281" cy="44" r="5"/></g>
            <circle className="evidence-review-node" cx="281" cy="119" r="5"/>
          </svg>
        </div>
        <div className="evidence-scene-beam" />
        <span className="evidence-pane-label evidence-label-source">来源</span>
        <span className="evidence-pane-label evidence-label-middle">证据</span>
        <span className="evidence-pane-label evidence-label-front">追溯</span>
      </div>
      <figcaption className="evidence-scene-caption">溯源概念演示 <span>·</span> 琥珀色线索待核验</figcaption>
      {!reducedMotion && (
        <button
          className="evidence-scene-toggle"
          type="button"
          onClick={() => setPaused((value) => !value)}
          aria-label={paused ? "播放证据窗动效" : "暂停证据窗动效"}
          aria-pressed={paused}
        >
          {paused ? "播放动效" : "暂停动效"}
        </button>
      )}
    </figure>
  );
}
