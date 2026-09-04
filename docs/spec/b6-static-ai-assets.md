# B6 static AI resource recognition

`app.detectors.detect_ai_assets(files)` consumes already-read relative-path text only. It detects explicit Hugging Face/ModelScope model or dataset URLs and OpenAI/Anthropic/Google client references.

Every detection emits a pending `AIAsset` plus file/line `Evidence`; it never calls an API, loads a model, infers authorization, or exposes credential-looking values in excerpts. Unsupported references are intentionally not guessed.
