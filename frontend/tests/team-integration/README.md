# Selected teammate integration regression

SYNTHETIC_TEST_ONLY. Mounts the real current P2Workbench, P2VersionComparison,
MaterialForm, materialBytes and p2.ts; only bottom fetch is synthetic. No backend,
source authentication, license approval or business acceptance is implied.

Twelve scenarios cover the exact saved parent; Binding/revision/data-scope/404
rejection; held parent GET on Assessment switch; material GET click races,
Assessment ABA, Result switch and unmount; an actually dispatched Material POST
whose 201 receipt survives unrelated GET cancellation; and passive readOnly GETs.

Unknown requests and all non-GET calls are independently recorded before dispatch.
Held responses are released through teardown. The positive Material write preserves
its actual serialized service body, CAS and idempotency key.

Build: TASK/helpers/integration-build.mjs. Runner:
TASK/helpers/integration-browser-runner.mjs with a fresh OPENGUARD_ATTEMPT_DIR.
Authentication is explicitly disabled for these component fixtures; account isolation
is verified separately by the root task.

Actual result: TASK/evidence/integration-browser-host2, 12/12, exit0, JUnit retained.
The prior host1 failure was two omitted exact r3 derived GET routes in this new
transport; its raw evidence remains, and no product assertion was removed.
