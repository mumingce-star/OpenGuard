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

## Implementation references

- React state organization: https://react.dev/learn/choosing-the-state-structure
- Contrast guidance: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- These informed state separation and visual review; the frontend does not claim full accessibility certification.

## P0 integration

Core pages reused from team commit 83e8928. Graph pages and React Flow dependencies were not imported. Existing React, Tailwind and Vite lockfile dependencies are unchanged.


## 2026-11-14 Gemini UI integration

The user supplied Gemini-generated TSX/CSS, including the inline authentication illustration and CSS SVG decorations. Codex reviewed these source changes and tested the integrated UI; no external artwork was downloaded and no dependency was added in this update. The exact Gemini model/version was not supplied. This entry records provenance, not an independent rights determination. Previously excluded landing video/poster remain excluded.

## 2026-11-15 Emerald evidence window

- Visual reference: https://reactbits.dev/components/glass-surface
- Usage: glass depth, edge highlights, and a light surface. The three evidence panes, paths, and motion are original React/CSS/SVG code; no React Bits source or external media was copied.
- Dependencies: none added. The scene is labeled as a concept demonstration and contains no measured scan result.

## 2026-11-16 Uiverse favorites in the pearl and forest-green theme

The user selected 22 favorites for this pass. OpenGuard uses its existing React components and original CSS/SVG adaptations for the original pass. The later landing CTA revision directly adapts the HTML/CSS supplied by the user from `cssbuttons-io / massive-mayfly-74`; its source and MIT notice are recorded below. No Uiverse assets, fonts, or runtime package were added. Forest green is the primary color; purple remains on copy and download controls. Motion follows reduced-motion preferences.

| Reference | OpenGuard placement |
| --- | --- |
| [andrew-manzyk / ancient-turtle-91](https://uiverse.io/andrew-manzyk/ancient-turtle-91) | Drawn-tick selection in shared checkboxes |
| [SelfMadeSystem / green-bobcat-29](https://uiverse.io/SelfMadeSystem/green-bobcat-29) | Compact P2 selection rows |
| [Admin12121 / soft-falcon-79](https://uiverse.io/Admin12121/soft-falcon-79) | GitHub/ZIP sliding segmented choice |
| [liyaxu123 / warm-eel-62](https://uiverse.io/liyaxu123/warm-eel-62) | Repository address floating label |
| [Lakshay-art / curvy-earwig-22](https://uiverse.io/Lakshay-art/curvy-earwig-22) | Search field focus glow |
| [cssbuttons-io / massive-mayfly-74](https://uiverse.io/cssbuttons-io/massive-mayfly-74) | Both landing CTAs: user-supplied `learn-more` structure and original expanding-circle/arrow/text transitions, scoped to the homepage and recolored to light sage |
| [satyamchaudharydev / quick-chicken-50](https://uiverse.io/satyamchaudharydev/quick-chicken-50) | Raised primary action and press states |
| [nazar-gavrylyk / evil-dragon-24](https://uiverse.io/nazar-gavrylyk/evil-dragon-24) | Download capsule with separate circular icon; resource and report header exports share a compact pearl-glass shell and muted lavender icon while preserving the recognizable silhouette |
| [adamgiebl / smart-moth-68](https://uiverse.io/adamgiebl/smart-moth-68) | Paper-plane send actions in P2 and assistant |
| [Mohammad-Rahme-576 / hard-starfish-64](https://uiverse.io/Mohammad-Rahme-576/hard-starfish-64) | Purple copy action and contextual hint |
| [Yaya12085 / yellow-goat-62](https://uiverse.io/Yaya12085/yellow-goat-62) | Dashed ZIP drop zone and hover state |
| [mobinkakei / grumpy-turtle-41](https://uiverse.io/mobinkakei/grumpy-turtle-41) | Staggered three-dot loading indicator |
| [vikas7754 / evil-mule-52](https://uiverse.io/vikas7754/evil-mule-52) | Raised help trigger and floating tooltip |
| [Smit-Prajapati / smart-liger-5](https://uiverse.io/Smit-Prajapati/smart-liger-5) | Layered evidence card on the product introduction page |
| [ElSombrero2 / tricky-robin-67](https://uiverse.io/ElSombrero2/tricky-robin-67) | Two-sided explanation card with explicit flip control |
| [barisdogansutcu / average-chipmunk-44](https://uiverse.io/barisdogansutcu/average-chipmunk-44) | Landing demo capsule with circular play area |
| [Praashoo7 / brave-moose-56](https://uiverse.io/Praashoo7/brave-moose-56) | Layered P2 form and task note surfaces |
| [vinodjangid07 / smart-emu-83](https://uiverse.io/vinodjangid07/smart-emu-83) | Remove action for unsent ZIP selection |
| [kamehame-ha / chilly-snake-91](https://uiverse.io/kamehame-ha/chilly-snake-91) | Overview navigation cards with grouped hover |
| [JkHuger / warm-panther-74](https://uiverse.io/JkHuger/warm-panther-74) | Task-list checkbox shape and completed state |
| [vinodjangid07 / thin-duck-22](https://uiverse.io/vinodjangid07/thin-duck-22) | Expanding logout icon pill |
| [Smit-Prajapati / spicy-rat-83](https://uiverse.io/Smit-Prajapati/spicy-rat-83) | Hovering OpenGuard brand story card |

Six other saved items remain outside this product mapping: bookmark, day/night toggle, star rating, Discord, social tooltip, and social-button group. None is presented as a business function.

## 2026-11-16 landing motion and glass refinement

The existing particle typography and React Bits Glass Surface design reference remain the only references for this pass. OpenGuard tightened its original Canvas timing and CSS/SVG glass material; no third-party source, asset, or runtime dependency was added.

## Uiverse landing CTA source notice

The homepage CTA structure and animation in `src/pages/Landing.tsx` and `src/styles/favorites-sage.css` adapt the code the user supplied from [cssbuttons-io / massive-mayfly-74](https://uiverse.io/cssbuttons-io/massive-mayfly-74). The same circle, arrow and text transition now appears on four primary workbench actions through `GlassArrowButton` in `src/components/ui.tsx`, with smaller sizing and the same pale glass palette. The OpenGuard version changes the colors, sizes, selectors, labels and click actions. The full MIT notice is in `UIVERSE_CSSBUTTONS_IO_LICENSE.txt` and is included in the built `third-party-licenses.txt`.

The later CTA glass edges, reflection and soft shadow are OpenGuard CSS tuned to match its existing evidence-window scene. They retain the source button's circle expansion, arrow and text transitions. No additional third-party source or runtime asset was added.
