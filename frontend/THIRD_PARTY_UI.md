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

2026-10-13 整合补记：以下是早期分支的历史使用记录。当前图谱使用 P1 后端契约实现，当前 package.json/pnpm-lock.yaml 不依赖 React Flow；历史声明文件保留供审计，不代表当前产品仍使用这些依赖。

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

## P0 integration

Core pages reused from team commit 83e8928. Graph pages and React Flow dependencies were not imported. Existing React, Tailwind and Vite lockfile dependencies are unchanged.

## 2026-10-13 团队首页媒体整合

- 来源：团队 `feat/p1-frontend-ui-upgrade@17b5998`，本地整合提交 `6486f94`；导入 `public/landing/openguard-hero-bg.mp4` 与 `public/landing/openguard-hero-poster.jpg`。
- 用途：`src/components/HeroBackground.tsx` 首页背景视频与海报。组件注明 Owner-authorized neural-landing media；本轮没有独立取得作者、生成工具或再分发授权原件，因此不据此宣称权利审核完成。
- 再分发门禁：素材 Owner 补充来源和可再分发授权回执；现有声明保留。无新增运行时依赖，也未下载外部新素材。
