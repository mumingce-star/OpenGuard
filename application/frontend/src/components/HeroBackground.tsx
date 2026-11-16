import { useEffect, useRef } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";

// Owner-authorized neural-landing media and playback policy, served locally.
export function HeroBackground() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (reducedMotion) {
      video.pause();
    } else {
      // Match the reference: autoplay rejection leaves the poster/static frame.
      void video.play().catch(() => {});
    }
    return () => video.pause();
  }, [reducedMotion]);

  return (
    <div className="hero-background" aria-hidden="true">
      <video
        ref={videoRef}
        className="hero-background-video"
        autoPlay={!reducedMotion}
        muted
        loop
        playsInline
        preload="auto"
        poster="/landing/openguard-hero-poster.jpg"
        src="/landing/openguard-hero-bg.mp4"
      />
      <div className="hero-background-veil" />
    </div>
  );
}
