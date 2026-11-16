import { useLayoutEffect, useRef } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";

type Particle = { x: number; y: number; dx: number; dy: number; color: string };
const palette = ["#134b3a", "#19614b", "#285c4f", "#2f8566"];
const duration = 800;

export function ParticleText({ text, className = "" }: { text: string; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const settled = useRef(false);
  const previousText = useRef(text);
  const reducedMotion = useReducedMotion();

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    if (previousText.current !== text) { previousText.current = text; settled.current = false; }
    if (reducedMotion) settled.current = true;

    let frame = 0;
    let particles: Particle[] = [];
    let size = { width: 0, height: 0, dpr: 0 };
    let visible = document.visibilityState === "visible";
    let inView = true;
    const started = performance.now();

    const draw = (now: number) => {
      const progress = settled.current || !visible || !inView
        ? 1 : Math.min(1, Math.max(0, (now - started) / duration));
      const remaining = (1 - progress) ** 3;
      context.clearRect(0, 0, size.width, size.height);
      for (const particle of particles) {
        context.beginPath();
        context.fillStyle = particle.color;
        context.arc(particle.x + particle.dx * remaining, particle.y + particle.dy * remaining, 1.45, 0, Math.PI * 2);
        context.fill();
      }
      frame = progress < 1 ? requestAnimationFrame(draw) : 0;
      if (progress === 1) settled.current = true;
    };

    const rebuild = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (!rect.width || !rect.height) return;
      if (size.width === rect.width && size.height === rect.height && size.dpr === dpr) return;
      if (size.width) settled.current = true;
      size = { width: rect.width, height: rect.height, dpr };
      cancelAnimationFrame(frame);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);

      const sample = document.createElement("canvas");
      sample.width = Math.max(1, Math.floor(rect.width));
      sample.height = Math.max(1, Math.floor(rect.height));
      const mask = sample.getContext("2d", { willReadFrequently: true });
      if (!mask) return;
      mask.fillStyle = "#fff";
      mask.font = '800 190px Inter, "Microsoft YaHei", sans-serif';
      const measuredWidth = mask.measureText(text).width;
      const fontSize = Math.min(190, (190 * Math.max(1, sample.width - 32)) / Math.max(1, measuredWidth));
      mask.font = `800 ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      mask.textAlign = "center";
      mask.textBaseline = "middle";
      mask.fillText(text, rect.width / 2, rect.height / 2);
      const pixels = mask.getImageData(0, 0, sample.width, sample.height).data;
      const gap = rect.width < 640 ? 5 : 4;
      const spread = rect.width < 640 ? 3 : 6;
      const next: Particle[] = [];
      for (let y = 0; y < sample.height; y += gap) {
        for (let x = 0; x < sample.width; x += gap) {
          if (pixels[(y * sample.width + x) * 4 + 3] <= 150) continue;
          const index = Math.floor(x / gap) * 17 + Math.floor(y / gap) * 31;
          const moving = index % 4 === 0;
          next.push({ x, y,
            dx: moving ? (((index * 37) % 101) / 50 - 1) * spread : 0,
            dy: moving ? (((index * 53) % 97) / 48 - 1) * spread : 0,
            color: palette[index % palette.length],
          });
        }
      }
      particles = next;
      draw(performance.now());
    };

    const visibility = () => {
      visible = document.visibilityState === "visible";
      cancelAnimationFrame(frame);
      frame = 0;
      if (!visible) settled.current = true;
      else draw(performance.now());
    };
    const viewport = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      if (!inView) { settled.current = true; cancelAnimationFrame(frame); frame = 0; }
      else if (!frame) draw(performance.now());
    }, { threshold: 0.08 });
    const resize = new ResizeObserver(rebuild);
    resize.observe(canvas);
    viewport.observe(canvas);
    document.addEventListener("visibilitychange", visibility);
    rebuild();

    return () => {
      resize.disconnect();
      viewport.disconnect();
      document.removeEventListener("visibilitychange", visibility);
      cancelAnimationFrame(frame);
    };
  }, [text, reducedMotion]);

  return <canvas ref={canvasRef} className={`particle-text ${className}`} role="img" aria-label={text}>{text}</canvas>;
}
