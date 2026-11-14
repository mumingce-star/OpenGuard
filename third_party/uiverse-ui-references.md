# Uiverse UI references — 2026-10-23

These 18 references were selected by the user from their favorites. OpenGuard implements its own React/SVG/CSS treatments; no author source files, package, image or font were imported. There is no third-party runtime dependency or package version for these design references. The source pages read on 2026-10-22 declared MIT; that declaration does not make OpenGuard's product data or reports MIT-licensed.

An upstream source-code SHA256 is **not applicable**: no upstream source artifact was acquired or copied. Implementation file hashes are recorded in the local acceptance receipt. If upstream code is imported in a later change, archive that exact source, hash it, and preserve its full author copyright and MIT text before inclusion.

The three features in each row are design targets implemented in OpenGuard, not a claim of pixel-identical reproduction. Current dynamic-source screenshots could not be signed off: public source captures encountered Cloudflare, and the existing in-app session timed out. Retain these failures; do not substitute a challenge screenshot for the original component. The approved plan's original-versus-product visual signoff remains pending user review.

| # | Author / source | Implemented design features | Integration |
|---|---|---|---|
| 1 | [andrew-manzyk / ancient-turtle-91](https://uiverse.io/andrew-manzyk/ancient-turtle-91) | rounded outline; drawn tick; selected fill | `Checkbox`: Graph, resource filters, Assessment history, P2 consent |
| 2 | [SelfMadeSystem / green-bobcat-29](https://uiverse.io/SelfMadeSystem/green-bobcat-29) | compact square; clear fill; dense labeled row | compact `Checkbox`: P2 subjects/Evidence |
| 3 | [Admin12121 / soft-falcon-79](https://uiverse.io/Admin12121/soft-falcon-79) | capsule track; moving selection; horizontal options | native radio `SegmentedControl`: GitHub/ZIP |
| 4 | [liyaxu123 / warm-eel-62](https://uiverse.io/liyaxu123/warm-eel-62) | underline; floating label; focus transition | repository field |
| 5 | [Lakshay-art / curvy-earwig-22](https://uiverse.io/Lakshay-art/curvy-earwig-22) | search icon; outlined inset surface; focus glow | History/Resources/Graph search |
| 6 | [cssbuttons-io / massive-mayfly-74](https://uiverse.io/cssbuttons-io/massive-mayfly-74) | circular arrow area; rounded CTA; arrow travel | landing and existing navigation actions |
| 7 | [satyamchaudharydev / quick-chicken-50](https://uiverse.io/satyamchaudharydev/quick-chicken-50) | dark body; bold label; colored hover/press | `ActionButton` primary; existing primary actions |
| 8 | [nazar-gavrylyk / evil-dragon-24](https://uiverse.io/nazar-gavrylyk/evil-dragon-24) | outlined capsule; purple circular icon; separate label zone | `DownloadControl`: P0/P1/parent Formal downloads; real GET busy/error/retry |
| 9 | [adamgiebl / smart-moth-68](https://uiverse.io/adamgiebl/smart-moth-68) | paper plane; solid rounded body; plane movement | P2 answer/material submit |
| 10 | [Mohammad-Rahme-576 / hard-starfish-64](https://uiverse.io/Mohammad-Rahme-576/hard-starfish-64) | purple capsule; icon/label; floating hint | Evidence/advice copy; no social sharing action |
| 11 | [Yaya12085 / yellow-goat-62](https://uiverse.io/Yaya12085/yellow-goat-62) | centered upload area; dashed perimeter; selected-file state | existing ZIP chooser/drop zone |
| 12 | [mobinkakei / grumpy-turtle-41](https://uiverse.io/mobinkakei/grumpy-turtle-41) | three circles; staggered bounce; readable waiting label | History/Graph/Profile/Report/P2 loading |
| 13 | [vikas7754 / evil-mule-52](https://uiverse.io/vikas7754/evil-mule-52) | raised trigger; floating panel; pointer | `HelpTip`: Graph filter, Profile version, report Hash |
| 14 | [Smit-Prajapati / smart-liger-5](https://uiverse.io/Smit-Prajapati/smart-liger-5) | layered surface; edge highlight; restrained depth | landing evidence card; stable resource-card surface |
| 15 | [ElSombrero2 / tricky-robin-67](https://uiverse.io/ElSombrero2/tricky-robin-67) | two faces; perspective rotation; separate reverse explanation | landing information-boundary cards; explicit accessible toggle |
| 16 | [barisdogansutcu / average-chipmunk-44](https://uiverse.io/barisdogansutcu/average-chipmunk-44) | circular play icon; capsule; contrasting icon/text | existing demo entry |
| 17 | [Praashoo7 / brave-moose-56](https://uiverse.io/Praashoo7/brave-moose-56) | dark rounded panel; inset fields; edge/shadow depth | P2 forms and task notes; no login added |
| 18 | [vinodjangid07 / smart-emu-83](https://uiverse.io/vinodjangid07/smart-emu-83) | trash glyph; hover movement; danger accent | remove unsent ZIP selection only |

Reduced motion disables decorative motion. Native input, disabled, focus and request semantics are retained. The separate `ui-preview.html` is explicitly a design sample, contains no business results and never submits to business APIs. Its static text download is not a report.

Deferred: day/night theme, rating, bookmarks, login/logout and social branding. Previously documented `spicy-rat-83` is not newly imported; its historical record is retained, with no new source-fidelity claim.

## 2026-10-24 project refinement

The existing references were adapted further within project-owned CSS: primary actions now use a cyan surface for hierarchy; New Scan uses a single form surface and a separate explanation column; the original landing video and particle title remain. No additional third-party code, assets or dependencies were acquired. Earlier source hashes identify the October 23 snapshot, not this uncommitted refinement.

Current SHA256: `frontend/src/components/ui.tsx` = `867a81311b9b5c80808850b4182e25010c826687722c70f77b9a3291ffac2067`; `frontend/src/styles/workspace.css` = `b9fe65a7ed66147070024ecdc913d02d391d98eaf92e196c42e4fccc3835b8f5`; `frontend/src/pages/Landing.tsx` = `94faa8daf16c6ab00dc29b1d3ff27cd856c2fe82478572dba47941cc338ed585`.

### 2026-10-24 result-page continuation

The preceding hashes identify the first refinement snapshot. Assessment/P2 authority surfaces, grouped inventory/history, Graph controls, report reading tools and task filters were subsequently refined in project-owned React/CSS. No new third-party code, assets, package or license was introduced. Source identity for this later uncommitted snapshot: `ui.tsx` SHA256 `e38f27c5f2c0cff38eaa171d20a1cf992c8eb8d624de1b6cf9d764210636e25b`; `workspace.css` SHA256 `736f2844c7316fc615f9dfd64f358fc74e11112bf6e12b2945efd6a38b92cf86`. Existing authorship/license records remain applicable; no new fidelity claim is made.

Final local result-page snapshot after fragment-navigation and sticky-directory verification: `workspace.css` SHA256 `9c2ed509ea7d93f74ac7bc93ecce6f13413f8664dd2042edb1a7bd1dc7e5e761`; `ui.tsx` unchanged from the preceding result-page hash. No new third-party acquisition.
