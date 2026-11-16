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

## 2026-11-16 半决赛录制界面选择性集成

来源：mumingce-star/OpenGuard，codex/landing-sage-ui，截止 3cee1edb160360b6dafc673f229bcd933a786887；主要视觉提交 07b6e3d5061fa8dea277c91bd0b03c92da3ceabb，含此前首页动画基础。保留原业务接线与许可记录。圆形箭头玻璃按钮改编自 cssbuttons-io / massive-mayfly-74（MIT），完整许可随 UIVERSE_CSSBUTTONS_IO_LICENSE.txt 和构建后的 third-party-licenses.txt 提供。未引入外部字体、媒体或运行依赖。
