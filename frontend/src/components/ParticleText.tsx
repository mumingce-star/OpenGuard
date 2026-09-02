import { useEffect, useRef } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

type Particle = {
  x: number;
  y: number;
  homeX: number;
  homeY: number;
  vx: number;
  vy: number;
  color: string;
};

type ParticleTextProps = {
  text: string;
  className?: string;
};

const palette = ['#f8fafc', '#c7d2fe', '#818cf8', '#22d3ee'];

export function ParticleText({ text, className = '' }: ParticleTextProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    let frame = 0;
    let particles: Particle[] = [];
    let pointer = { x: -9999, y: -9999, active: false };
    let visible = document.visibilityState === 'visible';

    const rebuild = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);

      const sample = document.createElement('canvas');
      sample.width = Math.max(1, Math.floor(rect.width));
      sample.height = Math.max(1, Math.floor(rect.height));
      const sampleContext = sample.getContext('2d', { willReadFrequently: true });
      if (!sampleContext) return;

      const maxSize = Math.min(190, rect.width / Math.max(text.length * 0.62, 1));
      const fontSize = Math.max(54, maxSize);
      sampleContext.fillStyle = '#ffffff';
      sampleContext.font = `800 ${fontSize}px Inter, "Microsoft YaHei", sans-serif`;
      sampleContext.textAlign = 'center';
      sampleContext.textBaseline = 'middle';
      sampleContext.fillText(text, rect.width / 2, rect.height / 2);
      const pixels = sampleContext.getImageData(0, 0, sample.width, sample.height).data;
      const gap = rect.width < 640 ? 5 : 4;
      const next: Particle[] = [];

      for (let y = 0; y < sample.height; y += gap) {
        for (let x = 0; x < sample.width; x += gap) {
          if (pixels[(y * sample.width + x) * 4 + 3] > 150) {
            const seed = (x * 17 + y * 31) % palette.length;
            next.push({
              x: x + (Math.random() - 0.5) * 36,
              y: y + (Math.random() - 0.5) * 36,
              homeX: x,
              homeY: y,
              vx: 0,
              vy: 0,
              color: palette[seed],
            });
          }
        }
      }
      particles = next;
    };

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      context.clearRect(0, 0, rect.width, rect.height);
      for (const particle of particles) {
        if (!reducedMotion && pointer.active) {
          const dx = particle.x - pointer.x;
          const dy = particle.y - pointer.y;
          const distance = Math.hypot(dx, dy);
          if (distance < 92 && distance > 0) {
            const force = (1 - distance / 92) * 1.9;
            particle.vx += (dx / distance) * force;
            particle.vy += (dy / distance) * force;
          }
        }
        particle.vx += (particle.homeX - particle.x) * (reducedMotion ? 1 : 0.045);
        particle.vy += (particle.homeY - particle.y) * (reducedMotion ? 1 : 0.045);
        particle.vx *= reducedMotion ? 0 : 0.82;
        particle.vy *= reducedMotion ? 0 : 0.82;
        particle.x += particle.vx;
        particle.y += particle.vy;
        context.beginPath();
        context.fillStyle = particle.color;
        context.arc(particle.x, particle.y, rect.width < 640 ? 1.2 : 1.45, 0, Math.PI * 2);
        context.fill();
      }
      if (!reducedMotion && visible) frame = requestAnimationFrame(draw);
    };

    const move = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top, active: true };
    };
    const leave = () => (pointer.active = false);
    const visibility = () => {
      visible = document.visibilityState === 'visible';
      cancelAnimationFrame(frame);
      if (visible && !reducedMotion) frame = requestAnimationFrame(draw);
    };

    const observer = new ResizeObserver(() => {
      rebuild();
      cancelAnimationFrame(frame);
      draw();
    });
    observer.observe(canvas);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerleave', leave);
    document.addEventListener('visibilitychange', visibility);
    rebuild();
    draw();

    return () => {
      observer.disconnect();
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerleave', leave);
      document.removeEventListener('visibilitychange', visibility);
      cancelAnimationFrame(frame);
    };
  }, [text, reducedMotion]);

  return <canvas ref={canvasRef} className={`particle-text ${className}`} aria-label={text} />;
}
