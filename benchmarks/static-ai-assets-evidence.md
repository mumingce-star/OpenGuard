# Static AI asset benchmark: reproducible evidence

This first P0 bench batch uses five tiny source-only cases rather than
redistributing model weights, datasets, or an external repository. All URLs
use fictional `acme/*` names: the benchmark tests the detector and evidence
contract, not a third-party resource's availability.

## Manual expectations

| Case | Expected resource | Evidence location | License / authorization evidence |
|---|---|---|---|
| `model-huggingface` | `model:huggingface:acme/demo-model` | `src/model.py:1` | unknown; URL observation only; authorization is `pending` |
| `dataset-huggingface` | `dataset:huggingface:acme/demo-dataset` | `src/data.py:1` | unknown; URL observation only; authorization is `pending` |
| `api-openai` | `api:openai:openai` | `src/client.py:1` | unknown; call reference is not a license or approval assertion |
| `model-modelscope` | `model:modelscope:acme/demo-model` | `config/resources.py:1` | unknown; URL observation only; authorization is `pending` |
| `negative-generic-url` | none | `docs/readme.md:1` | negative control; a generic URL must not become an AI asset |

The case definition is [static-ai-assets-v1.json](cases/static-ai-assets-v1.json).
`expected` preserves the scanner teammate's labels from implementation `1c7239e` (branch tip `89c8ba2`). Root inspected the five snippets and independently exercised the ZIP and HTTP paths; independent human double annotation is still pending. `predicted`, `assets` and `evidence` are generated from the current detector, not hand-written predictions.

## Run and verify

Use the existing project Python environment; no new package dependencies are required.

```bash
PYTHONPATH=backend python -c "from benchmarks.run_static_assets import write_result; write_result('benchmarks/cases/static-ai-assets-v1.json', 'benchmarks/results/static-ai-assets-v1.actual.json')"
PYTHONPATH=backend python -c "from benchmarks.evaluate import evaluate_scan_result; print(evaluate_scan_result('benchmarks/results/static-ai-assets-v1.actual.json'))"
PYTHONPATH=backend python -m pytest -q tests/unit/test_benchmark_actual_static_assets.py tests/security/test_a4_ai_assets_independent.py
# Existing Compose with AI disabled, before running this batch:
OPENGUARD_ENABLE_AI=0 OPENGUARD_OLLAMA_DOCKER_HOST=0 docker compose -f deploy/compose.yaml up -d --no-deps --wait api
PYTHONPATH=. python3 deploy/smoke.py --bench-cases benchmarks/cases/static-ai-assets-v1.json --output /tmp/openguard-scanner-bench
# Validate these same scan IDs after a restart; do not submit again:
PYTHONPATH=. python3 deploy/smoke.py --bench-cases benchmarks/cases/static-ai-assets-v1.json --output /tmp/openguard-scanner-bench --verify
```

Current recorded detector output: [static-ai-assets-v1.actual.json](results/static-ai-assets-v1.actual.json), regenerated on 2026-09-06 with `openguard-static-ai-detector/0.1.1`.
SHA-256: `a66320164f14741b843341e42d5e3c2c5d575199d6af3d3b5cb02c861731bd0f`.
The unchanged five cases yield TP=4, FP=0, FN=0, micro precision/recall/F1=1.0. The generic-URL negative has TP/FP/FN=0 and no false detection; its own zero-denominator metrics are defined as zero. These are synthetic recognition results, not production accuracy or legal conclusions.

The upstream result with scanner 0.1.0 and SHA `b39265e6c99b465fd0a82fcf5ad9b53a43516326f7616d93babd850aae00b99a` remains historical evidence on commit `1c7239e`; it is not represented as the current run.

## Current product-path acceptance

All four positive snippets reached `completed` through deployed Linux Compose ZIP ingestion, the existing real ScanCode/Syft configuration, static detection, pending risk/Evidence and four report formats. Every AI-asset evidence hash and line was checked against its source snippet. The API reference `openai.responses` was visible in Chrome at `src/client.py:1`, with NOASSERTION and a review-required risk. No provider was called for this batch.

The negative snippet has no supported resource and therefore honestly ends `failed/scan` with `dependency_manifest_not_found`, a zero resource summary and `409 scan_not_ready` when requesting resources. It does not generate a report. The first HTTP verifier incorrectly expected an empty resource response; only that expectation was corrected, then the same five scan IDs were verified without rescanning. The product API was not changed.

Relevant regression suite: 159 passed. An initial invocation had an incorrect existing test filename and ran no tests; the corrected file list produced the stated result. The evaluator also checks non-perfect TP/FP/FN and proves that changing expected labels cannot change predicted labels. This does not certify all evaluator inputs or broader recognition coverage.

## Tool boundary and known limits

- This B6 output runs only the offline static detector. It does not execute the
  sample, call providers, download a model/dataset, or infer a license.
- Existing external-tool evidence is ScanCode `32.5.0` and Syft `1.51.0`.
  They are separate B2/B3 adapters and did not create this B6 output.
- The upstream Windows run only covered the detector. This integration additionally verified the existing Linux Compose path on the current Mac host. Stranger-machine deployment, broader real-repository labels and AI suggestion quality remain unverified.
