# Voice Core Bundle

This directory is the release-time intake point for the zero-install local voice bundle.

Do not commit model weights or native runtime binaries here during source development. A production package must populate this directory with the files listed in `manifest.json`, then run bundle verification before release.

Required production components:

- Kokoro EN ONNX runtime wrapper, model, and `af_heart`/`af_bella` voice pack.
- Piper Linux x64 runtime plus `nl_NL-mls-medium` ONNX model/config.
- Whisper.cpp runtime plus `ggml-base.en.bin`.
- Silero VAD ONNX model.
- License files, checksums, and sample WAVs.

At runtime the app verifies or copies this bundle into `${AI_HOME}/voice-core`. Missing files must report `bundle_missing`, `runtime_missing`, `model_missing`, or `bundle_corrupt`; never report `ready`.
