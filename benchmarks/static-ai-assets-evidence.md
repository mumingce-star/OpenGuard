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
`expected` is the human-reviewed label list. `predicted`, `assets`, and
`evidence` in the result are scanner-generated, so the evaluator does not
score a hand-written prediction.

## Run and verify

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -c "from benchmarks.run_static_assets import write_result; write_result('benchmarks/cases/static-ai-assets-v1.json', 'benchmarks/results/static-ai-assets-v1.actual.json')"
.\.venv\Scripts\python.exe -c "from benchmarks.evaluate import evaluate_scan_result; import json; print(json.dumps(evaluate_scan_result('benchmarks/results/static-ai-assets-v1.actual.json'), ensure_ascii=False, indent=2))"
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_benchmark_actual_static_assets.py
```

Recorded actual output: [static-ai-assets-v1.actual.json](results/static-ai-assets-v1.actual.json), generated on 2026-09-06 with `Python 3.12.10` and scanner identifier `openguard-static-ai-detector/0.1.0`.
SHA-256: `b39265e6c99b465fd0a82fcf5ad9b53a43516326f7616d93babd850aae00b99a`.
Its score is `TP=4`, `FP=0`, `FN=0`, `precision=1.0`, `recall=1.0`, `F1=1.0` for these five synthetic cases only; it is not a production-accuracy claim.

## Tool boundary and known limits

- This B6 output runs only the offline static detector. It does not execute the
  sample, call providers, download a model/dataset, or infer a license.
- Existing external-tool evidence is ScanCode `32.5.0` and Syft `1.51.0`.
  They are separate B2/B3 adapters and did not create this B6 output.
- The descriptor-safe ZIP-to-tool end-to-end path requires POSIX capabilities.
  It is intentionally not claimed as verified on this Windows host. Linux
  verification and broader independent/repository benchmark coverage remain open.
