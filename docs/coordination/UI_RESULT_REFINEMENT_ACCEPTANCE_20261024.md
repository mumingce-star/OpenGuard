# Result-page UI refinement — local acceptance, 2026-10-24

Implementation and local browser checks passed. User visual approval and live backend verification remain pending. Source is the uncommitted working tree on `codex/uiverse-ui-upgrade`, based on `2ee6003877e38a248b46fb21fc7cbcd7d5931eea`. No new commit, push, merge or deployment occurred.

## Changes delivered in the requested order

| Step | Result | Main files |
|---|---|---|
| 1 — Assessment/P2 | Formal Assessment comes first; native section links reach obligations, AI and the independent P2 result; distinct cyan/purple/amber surfaces keep authority boundaries readable | `Assessment.tsx`, `P2Workbench.tsx`, `ui.tsx`, `workspace.css` |
| 2 — History/Resources/Graph | History rows use clearer groups; resource filters and displayed-item count share a surface; Profile technical identity can expand; Graph toolbar, keyboard guidance and details have clearer hierarchy | `Resources.tsx`, `AIResourceCard.tsx`, `Graph.tsx`, `workspace.css` |
| 3 — Report/Remediation | Saved report body appears earlier; creation/snapshot controls collapse while reading and expose errors; report directory and print styles refined; task state tiles use the existing URL filter and loaded task counts | `ReportV2.tsx`, `Remediation.tsx`, `workspace.css` |

The current work retains the preceding uncommitted Landing/New Scan/navigation refinement. Existing data handlers for Formal, P2, report retry/idempotency and task PATCH/CAS are retained. `hooks/useRoute.ts` now respects an existing fragment destination during browser history restoration instead of resetting every such jump to the page top. No changes to backend, public schema, frontend service/type contracts, dependencies or lockfiles.

## Executed verification

| Verification | Actual result and limit |
|---|---|
| Frontend unit suite | 148 PASS, 0 FAIL, 0 SKIP, rerun after the fragment-navigation fix |
| TypeScript + production build | PASS; final Vite build has 63 modules; rerun after the mobile tooltip and section-offset fixes |
| Existing UI browser suite | 13 groups PASS: native controls, motion, navigation, download failure/retry/bytes, print and GET-only audit. Rerun after the route fix; the final report-directory sticky-offset-only CSS correction was subsequently checked by the result-page suite |
| Existing P2 browser fixture | 11 groups PASS; 78 intercepted requests including 4 simulated POSTs; no live outbound API traffic. Includes retry, version conflict, material/result readback, URL restoration and Formal unchanged |
| New result-page browser suite | 6 groups PASS on the final build: Formal/P2 ordering and anchors; resource identity; Graph scale and keyboard; task URL filter/reload; report body/print; six pages at 1440/1024/390px |
| Graph isolated layout timing | 100 nodes: 116 ms; 300 nodes: 174 ms; 500 nodes: 182 ms. Exact fixture edges checked. Includes navigation/render wait on this receiver; not a production throughput benchmark |
| Errors and writes | New suite: zero pageerrors, zero unexpected requests, zero mutations; every request intercepted |
| Preview | Homepage, New Scan and History return HTTP 200 at localhost:4189; existing preview process serves the final build |
| Diff check | `git diff --check` passed; main worktree's three pre-existing modifications remain |

The new harness uses recorded TEST_ONLY P2 HTTP responses, declared History/Graph fixtures, four task states, one long-ID/missing-Profile card and a fixed report reading sample. All screenshots carry a visible TEST_ONLY label. These responses exist only inside the isolated test harness. Product API mode has no success-fixture fallback.

Print verification confirms visible body content and hidden controls in browser print media; it does not certify physical printer output or all-page pagination. Existing iframe source and print action remain unchanged. The final anchor checks also confirm the fixed header does not cover the destination heading.

## Failures retained and resolved

1. The initial Graph screenshot failed because the shared integration fixture contains nonempty `provenance.assessment_refs`, while the existing frozen facts-only UI parser explicitly rejects those references. The test adapter removes only that fixture provenance field's entries and validates the adapted fixture with the unchanged production parser. No product validator was relaxed. Live Graph compatibility with the latest backend remains unverified.
2. At 390px the report's hidden Hash tooltip extended the page to 448px. The report-specific mobile tooltip now anchors to the right with a bounded width. Both hidden and explicitly opened tooltip states pass the unchanged no-overflow assertion.
3. Visual inspection found section headings could move under the fixed top bar. A 95px scroll margin now keeps Assessment/P2, report and task destinations visible; the report directory also stays below that bar.
4. Final screenshot inspection revealed that checking only a destination's lower Y bound did not prove it was in the viewport. The existing route's popstate handler reset native fragment navigation to the page top. The route now scrolls to an existing fragment target; the strengthened test waits for the heading between the fixed header and the middle of the viewport. Assessment/P2 and Report checks pass, and screenshots visibly show the target headings and report body. Earlier successful but insufficient checks remain recorded as intermediate evidence, not final proof.

Original failed screenshots remain in `output/result-ui-20261024/browser/`, `browser-v2/` and `browser-v3/` in the primary workspace. Final successful evidence is in `delivered/`; intermediate `verified/`, `final/` and `closed/` evidence is retained.

## Reproducible evidence

Run `node tests/result-ui-browser.mjs` from `frontend/` with existing Playwright resolution in `OPENGUARD_PLAYWRIGHT`, recorded input in `P2_HTTP_EVENTS`, a fresh ignored `OPENGUARD_QA_OUTPUT`, and optional `OPENGUARD_UI_BASELINE` pointing to the prior build. The harness intercepts all traffic and refuses unexpected methods or missing fixtures.

Primary workspace, ignored local outputs:

- `output/result-ui-20261024/delivered/receipt.json`: six checks, timings and exact request audit.
- Same directory: `before-*.png` and corresponding result-page screenshots at the same 1440×1000 viewport; `p2.png`, `task-states.png`, `graph-500.png`, `report-body.png`, `report-print.png`, and six `*-mobile.png` screenshots.
- `output/result-ui-20261024/ui-closed/receipt.json`: existing UI suite, rerun after the route fix.
- `output/result-ui-20261024/p2-closed/receipt.json`: existing P2 fixture suite, rerun after the route fix.
- `output/result-ui-20261024/baseline-dist/`: preceding round's built UI, preserved for comparison.

## Source identity

SHA256 of uncommitted files; these are file hashes, not Git commit IDs:

| File | SHA256 |
|---|---|
| `frontend/src/components/ui.tsx` | `e38f27c5f2c0cff38eaa171d20a1cf992c8eb8d624de1b6cf9d764210636e25b` |
| `frontend/src/styles/workspace.css` | `9c2ed509ea7d93f74ac7bc93ecce6f13413f8664dd2042edb1a7bd1dc7e5e761` |
| `frontend/src/hooks/useRoute.ts` | `d7ff40ab1b3f106ef77b41a455cc7f5a312d2cb3243ea84b5b6f3a4ca75e560d` |
| `frontend/src/pages/Assessment.tsx` | `4f0231a2bd991ef3e4a9fe9a007ba645429d9e6df2edfe26e87d1b4193602a3f` |
| `frontend/src/pages/ReportV2.tsx` | `e91fca63182887994fa27dccfa420f90be66c8fae8971f605d02b33df4db1fd9` |
| `frontend/tests/result-ui-browser.mjs` | `00673ccfe9a7b9a4776c3fdd76589be9ba707b549ff4bc52ca3caae54dc51a26` |

## Pending acceptance

User visual approval remains pending. Backend port 8082 is offline: live API identity, GET server-side effects, real report downloads, actual CAS and database persistence were not revalidated by this UI round. Existing team gates for production NOTICE, human review, evaluation, integration compatibility and release remain with their original owners. No whole-project completion percentage is asserted.

Preview: <http://127.0.0.1:4189/>. Populated result-page evidence is in the clearly labeled isolated screenshots while the backend is offline.

No additional third-party code, assets or packages were acquired. Existing Uiverse references remain design influences; this round refines project-owned React/CSS. Exact token usage is unavailable; the opening estimate was 12,000–24,000 tokens, and actual range compliance cannot be measured.

## Later live closeout — 2026-10-24

The backend-offline statement above records the earlier refinement run. Existing receiver services were subsequently restored without rebuilding or replacing data. The same UI source passed seven groups of live, GET-only checks across P1 acceptance_synthetic, fixed acceptance_real_reviewed Obligation and TEST_ONLY P2 instances. Report browser-download hashes match the fixed handoff, and all three database/WAL hash sets remained unchanged. See `UI_LIVE_CLOSEOUT_RECEIPT_20261024.md` for exact scope, expected legacy 404/P0 409 states and receiver evidence. User visual acceptance and Git upload authorization remain pending; this does not close team-wide release gates.
