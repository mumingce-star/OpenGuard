# UI refinement local acceptance — 2026-10-24

Status: implementation and local UI checks passed; user visual acceptance pending. No new commit, push, merge or deployment.

Source: `codex/uiverse-ui-upgrade`, based on `2ee6003877e38a248b46fb21fc7cbcd7d5931eea`, with the uncommitted refinement described here. This is not a new Git revision.

## Changes

- New Scan: a single form surface with a separate explanatory column; optional usage controls and scan boundaries remain available; missing selected-tab input keeps submission disabled.
- Navigation: 208px sidebar can collapse to 76px; widths at or below 1100px use the existing accessible navigation dialog.
- Landing: existing animated video and particle title retained; clearer cyan primary CTA, shorter supporting copy, less repetitive bottom content and lighter workflow framing.
- Shared surfaces and primary buttons: restrained borders and cyan action hierarchy. Existing download treatment, API calls, request locks, state meanings and Formal boundaries retained.

## Executed verification

| Check | Result |
|---|---|
| Frontend unit tests | 148 passed, 0 failed, 0 skipped, rerun October 24 |
| TypeScript and production build | Passed; Vite 63 modules |
| Isolated Chromium UI smoke | 13 scenario groups passed |
| Navigation | 76px collapsed rail; 1024/786/390px drawer; Escape and focus restoration passed |
| Motion | Video time advances and particle canvas renders; reduced-motion pauses video |
| Downloads | Explicit 503 failure, double-click lock, retry and exact sample bytes passed |
| Print | Explicit demo report body remains visible; controls hidden |
| Request audit | No pageerrors; all intercepted requests GET |
| Representative contrast | Body 14.66:1; muted text 9.32:1; search boundary 4.13:1; checkbox outline 6.39:1 |
| Preview | Homepage and New Scan HTTP 200 on localhost:4189 |

The browser suite deliberately serves test 503 responses for business APIs. It does not supply synthetic success responses in API mode. Demo report checks use the explicitly marked demo mode. This is UI evidence, not formal backend acceptance or a whole-site accessibility certification.

The previous immediate sidebar-width assertion failed with 208 instead of 76. It now waits for the expected layout before asserting the same 76px requirement; the bounded wait and subsequent assertion passed. Previous failed-run evidence is preserved. No production layout workaround was introduced for that failure.

Local evidence in the primary workspace's ignored output directory:

- `output/ui-refinement-20261023/baseline-dist/`: original built UI for comparisons.
- `output/ui-refinement-20261023/final/`: previous interrupted/failed verification artifacts.
- `output/ui-refinement-20261024/verified/receipt.json`: checks, request audit and contrast values.
- Same directory: `before-landing-viewport.png`, `landing-viewport.png`, `before-new-scan.png`, `new-scan-upload.png`, `new-scan-390.png`, `landing-motion.png`, `report-print.png`.

## Remaining boundaries

User visual approval remains pending. Backend port 8082 was not listening during this run; live scan/API acceptance was not performed. Original Uiverse dynamic comparison, latest integration compatibility and the team's existing production/competition gates remain separate. No backend, public schema, service DTO, dependency or lockfile changed.

Preview: <http://127.0.0.1:4189/> and <http://127.0.0.1:4189/app/new-scan?mode=api>.
