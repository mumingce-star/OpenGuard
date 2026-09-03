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

No paid prompt, restricted template, paid component source, icon pack or image is copied into this frontend. Open-source runtime packages are installed through the lockfile and listed below.

## React Bits — Glow Cursor

- Reference: https://reactbits.dev/animations/glow-cursor
- Usage: visual reference for the cyan-to-violet cursor trail on the landing page.
- Implementation: `src/components/GlowCursor.tsx` is an original Canvas 2D implementation. It does not copy or redistribute React Bits component source, keeps pointer events available to the page, pauses in background tabs, and disables itself for coarse pointers and reduced-motion users.

## React Flow — evidence graph (2026-09-03)

- Package: @xyflow/react 12.11.6; official source: https://reactflow.dev/learn and https://github.com/xyflow/xyflow
- License: MIT, verified against the installed package LICENSE; retain upstream copyright/permission notice.
- Usage: lazy-loaded evidence relationship canvas, zoom/pan/reset and node selection. Domain relations, page layout and evidence reader remain OpenGuard frontend code.
- No Pro template or paid example source is copied. Default React Flow attribution remains visible.
- Runtime dependency licenses are preserved in public/THIRD_PARTY_NOTICES.txt and copied to dist by Vite.
- The lockfile includes @xyflow/system, Zustand, classcat and D3 dependencies; their exact versions and MIT/ISC/BSD notices are included in that file.
- use-sync-external-store is overridden to 1.6.0 in pnpm-workspace.yaml because 1.2.0 declares no React 19 peer support. Version 1.6.0 declares React 19 support; pnpm peers check passes.

## Implementation references

- React state organization: https://react.dev/learn/choosing-the-state-structure
- Contrast guidance: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- These informed state separation and visual review; the frontend does not claim full accessibility certification.
