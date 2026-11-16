import { useEffect, useRef } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

type TrailPoint = {
  x: number;
  y: number;
  life: number;
};

const HEAD_COLOR = { r: 103, g: 232, b: 249 };
const TAIL_COLOR = { r: 167, g: 139, b: 250 };

function mixColor(progress: number) {
  const r = Math.round(TAIL_COLOR.r + (HEAD_COLOR.r - TAIL_COLOR.r) * progress);
  const g = Math.round(TAIL_COLOR.g + (HEAD_COLOR.g - TAIL_COLOR.g) * progress);
  const b = Math.round(TAIL_COLOR.b + (HEAD_COLOR.b - TAIL_COLOR.b) * progress);
  return `${r}, ${g}, ${b}`;
}

export function GlowCursor() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || reducedMotion || window.matchMedia('(pointer: coarse)').matches) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    let animationFrame = 0;
    let lastTime = performance.now();
    let lastPointer: { x: number; y: number } | null = null;
    let active = false;
    let pageVisible = document.visibilityState === 'visible';
    const points: TrailPoint[] = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const addPoint = (x: number, y: number) => {
      if (lastPointer) {
        const dx = x - lastPointer.x;
        const dy = y - lastPointer.y;
        const distance = Math.hypot(dx, dy);
        const steps = Math.min(6, Math.floor(distance / 12));
        for (let step = 1; step <= steps; step += 1) {
          const progress = step / (steps + 1);
          points.push({ x: lastPointer.x + dx * progress, y: lastPointer.y + dy * progress, life: 1 });
        }
      }
      points.push({ x, y, life: 1 });
      if (points.length > 34) points.splice(0, points.length - 34);
      lastPointer = { x, y };
    };

    const onPointerMove = (event: PointerEvent) => {
      active = true;
      addPoint(event.clientX, event.clientY);
    };

    const onPointerLeave = () => {
      active = false;
      lastPointer = null;
    };

    const drawTrail = (width: number, opacity: number, blur: number) => {
      if (points.length < 2) return;
      context.save();
      context.globalCompositeOperation = 'lighter';
      context.lineCap = 'round';
      context.lineJoin = 'round';
      context.shadowBlur = blur;

      for (let index = 1; index < points.length; index += 1) {
        const from = points[index - 1];
        const to = points[index];
        const progress = index / Math.max(1, points.length - 1);
        const alpha = Math.min(from.life, to.life) * opacity * Math.pow(progress, 0.7);
        if (alpha <= 0.01) continue;
        const color = mixColor(progress);
        context.beginPath();
        context.strokeStyle = `rgba(${color}, ${alpha})`;
        context.shadowColor = `rgba(${color}, ${Math.min(1, alpha * 1.45)})`;
        context.lineWidth = width * (0.36 + progress * 0.64);
        context.moveTo(from.x, from.y);
        context.quadraticCurveTo(from.x, from.y, (from.x + to.x) / 2, (from.y + to.y) / 2);
        context.stroke();
      }
      context.restore();
    };

    const draw = (time: number) => {
      const delta = Math.min(48, time - lastTime);
      lastTime = time;
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
      const decay = delta / (active ? 620 : 400);
      for (const point of points) point.life -= decay;
      while (points.length && points[0].life <= 0) points.shift();

      drawTrail(18, 0.13, 24);
      drawTrail(8, 0.36, 13);
      drawTrail(2.2, 0.92, 5);

      const head = points.at(-1);
      if (head && head.life > 0) {
        context.save();
        context.globalCompositeOperation = 'lighter';
        const halo = context.createRadialGradient(head.x, head.y, 0, head.x, head.y, 18);
        halo.addColorStop(0, `rgba(224, 251, 255, ${head.life * 0.92})`);
        halo.addColorStop(0.18, `rgba(103, 232, 249, ${head.life * 0.52})`);
        halo.addColorStop(1, 'rgba(103, 232, 249, 0)');
        context.fillStyle = halo;
        context.beginPath();
        context.arc(head.x, head.y, 18, 0, Math.PI * 2);
        context.fill();
        context.restore();
      }

      if (pageVisible) animationFrame = requestAnimationFrame(draw);
    };

    const onVisibilityChange = () => {
      pageVisible = document.visibilityState === 'visible';
      cancelAnimationFrame(animationFrame);
      if (pageVisible) {
        lastTime = performance.now();
        animationFrame = requestAnimationFrame(draw);
      }
    };

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    document.documentElement.addEventListener('mouseleave', onPointerLeave);
    document.addEventListener('visibilitychange', onVisibilityChange);
    animationFrame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animationFrame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
      document.documentElement.removeEventListener('mouseleave', onPointerLeave);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [reducedMotion]);

  return <canvas ref={canvasRef} className="glow-cursor-canvas" aria-hidden="true" />;
}
