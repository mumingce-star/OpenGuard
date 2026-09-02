# Third-party UI and visual references

## React Bits — Particle Text

- Reference: https://reactbits.dev/text-animations/particle-text
- Current availability checked: React Bits Pro component
- License note: the public React Bits repository uses MIT + Commons Clause; Pro component source was not copied or redistributed.
- Usage: visual reference for the landing-page particle typography.
- Implementation: `src/components/ParticleText.tsx` is an original Canvas 2D implementation written for OpenGuard. It samples a text mask, animates particles back to home positions, adds pointer repulsion, pauses when the page is hidden, and renders statically for reduced-motion users.

## Tailwind CSS

- Source: https://tailwindcss.com/
- License: MIT
- Usage: Vite integration and shared theme foundation.

No paid prompt, restricted template, icon pack, image, or third-party component source is bundled in this frontend.

## React Bits — Glow Cursor

- Reference: https://reactbits.dev/animations/glow-cursor
- Usage: visual reference for the cyan-to-violet cursor trail on the landing page.
- Implementation: `src/components/GlowCursor.tsx` is an original Canvas 2D implementation. It does not copy or redistribute React Bits component source, keeps pointer events available to the page, pauses in background tabs, and disables itself for coarse pointers and reduced-motion users.
