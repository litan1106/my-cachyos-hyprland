# BFS on RX 9060 XT

For step-by-step browser use and the portrait/1080p workflow plan, read the [user guide](USER_GUIDE.md). For likeness, motion, and integration adjustments, read the [tuning guide](TUNING_GUIDE.md).

An experimental [two-reference browser workflow](workflows/bfs-v3-rx9060xt-x.json) is available with [usage instructions](TUNING_GUIDE.md#use-two-reference-photos). Its graph and guide composition are checked; a two-photo model render and likeness improvement remain unverified.

This project runs the BFS author's V3 persistent-reference workflow with LTX-2.3 in an isolated ComfyUI environment on the RX 9060 XT. The locked ROCm runtime, finite FP32/BF16 kernels, four pinned node packs, all six selected model artifacts and actual frontend/API export parity have been verified. Short public-sample renders complete through ComfyUI history and pass metadata, full decoding and browser playback checks. Quality acceptance remains open.

The adapted files in `workflows/` now load the full source at 24 FPS (`frame_load_cap: 0`) and pass source audio directly to conditioning and export, with no fixed-duration trim. Resolution remains a 512 × 320 source area plus a 128-pixel reference panel (640 × 320 composed), with batch size 1. Only the earlier 33-frame workload has completed render validation; uncapped full-length rendering is not yet validated. Q3 transformer and Q4 Gemma are local memory adaptations, with matching LTX-2.3 projection/VAEs and the adaptive V3 LoRA initially at 1.0. Their quality relative to higher precision is unmeasured. Preserve the pinned `workflows/bfs-v3-upstream.json` unchanged.

The author graph's active `bong_tangent` scheduler is registered by RES4LYF, which is outside the four installed packs. The adapted graph uses `ManualSigmas` with eight-step FP32 values verified against the [pinned implementation](https://github.com/ClownsharkBatwing/RES4LYF/blob/6780724de0ddb98e7454d54bb80387836a911ece/sigmas.py). The author workflow does not record its scheduler-extension revision, so this pin is an explicit local assumption. Evidence is in `logs/schedule-equivalence.json`. Changing the step count requires regenerating that curve. The uncapped UI graphs were imported and exported through the actual frontend, with exact API parity recorded in `logs/full-length-frontend-export-check.json` and `logs/full-length-multiref-frontend-export-check.json`. Live schema and generator checks are in `logs/full-length-workflow-check.json`; these checks do not execute a model render.

## Setup and models

The installer checks the pinned source revisions, synchronizes the locked environment, verifies GPU kernels, optionally downloads the selected models, and starts the UI:

```bash
./install-bfs.sh --models --start
```

For an existing installation, `./install-bfs.sh --check` verifies sources, dependencies and GPU computation without synchronizing packages; add `--models` for read-only model integrity checks. Existing checkouts with local changes or different revisions are preserved and reported. Missing checkouts are cloned at the recorded commits. System prerequisites such as ROCm, `uv` and FFmpeg must already be installed.

To start with an experimental profile, use `./install-bfs.sh --models --start --profile gpu-text`. The `--profile` option requires `--start`; omitting it uses `legacy`.

From the project root, use Python 3.12 and the project-local environment:

```bash
uv sync --locked
export ROCM_PATH=/home/litan/.local/opt/rocm-10.0.0-gfx120X-all
export HIP_PATH="$ROCM_PATH"
export LD_LIBRARY_PATH="$ROCM_PATH/lib:$ROCM_PATH/lib/llvm/lib"
HIP_VISIBLE_DEVICES=0 .venv/bin/python scripts/check-gpu.py
.venv/bin/python scripts/download-models.py --verify
```

The 2026-11-12 migration uses AMD's exact ROCm 10.0.0 SDK in that user-owned prefix and matching AMD PyTorch 2.13.0, torchvision 0.28.0, torchaudio 2.11.0.2 and Triton wheels. Python remains 3.12; finite FP32/BF16 kernels and dependency/import checks pass. PyTorch loads its ROCm 10.0 SDK wheel libraries. The subsequent cleanup removed all 44 pacman packages in the ROCm 7.2 dependency closure and the old `/opt/rocm` prefix. The separate system ROCm PyTorch/ONNX Runtime packages were removed with that closure; this project retains its verified ROCm 10 virtual environment. The launcher, installer, monitoring tools and profiler now default to the ROCm 10 SDK, and new interactive Bash shells export that prefix. See the [installation and recovery guide](../my-cachyos-hyprland/docs/rocm-install-arch.md) and [migration evidence](logs/rocm-10.0-upgrade/20261113T034906Z/).

The manifest records pinned model revisions, sizes and checksums. To explicitly download the selected required models, run:

```bash
.venv/bin/python scripts/download-models.py
```

The downloader checks space and retains at least 50 GB free. Optional models are selected explicitly by manifest ID; for example:

```bash
.venv/bin/python scripts/download-models.py --model lora_rank64
.venv/bin/python scripts/download-models.py --verify --model lora_rank64
```

Keep model credentials outside project files and logs. A verified download does not prove the graph fits memory or loads successfully.

The optional `transformer_fp8` LTX-2.3 model has been downloaded and its size and SHA-256 verified ([record](logs/optimization-fp8-verification.json)). Its loader, memory fit, performance, and output quality have not yet been established by a native-format render.

## Launch and inputs

```bash
./run-bfs.sh
```

The default `legacy` profile retains the original launch settings. Inspect its exact command with `./run-bfs.sh --print-command`. Experimental profiles are listed in `config/runtime-profiles.json`; for example, `./run-bfs.sh --profile gpu-text` removes `--lowvram` while retaining the legacy memory manager. Profile names describe experiments and do not establish a speed or quality improvement. The launcher refuses an occupied port and never stops another server.

The launcher allows uploads up to 4 GiB (`--max-upload-size 4096`). Restart the project server after changing launch settings.

For a whole movie, use the experimental [long-video runner](USER_GUIDE.md#9-process-an-entire-long-video) rather than raising the graph's frame limit. It processes sequential 33-frame jobs at 24 FPS, records progress, and joins the results with the source audio. Its working/output resolution remains small; it does not enable native 1080p generation. Full-movie quality and multi-day endurance remain unverified.

A two-job NASA excerpt test verifies stop/resume without duplicate jobs, 66 joined frames at 24 FPS, aligned source audio, full decoding and browser playback. Quality fails on that excerpt: BFS inserts a person into a launch-pad shot without a person, and the generated framing changes at the chunk boundary. It has no face-presence/target-person filter; review the [record](logs/long-video-verification.json) before attempting unattended movie processing.

Open <http://127.0.0.1:8189>. Import the adapted UI workflow `workflows/bfs-v3-rx9060xt.json`; the unchanged upstream copy is for reference. Prepare a continuous source shot and a clear reference, inspect the composed guide, and record input hashes and selected range using [input preparation](.agent/skills/bfs-prepare-inputs/SKILL.md). Follow the [author's guide](https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap-Video) for the selected version. Use a manual V3 prompt in the graph with `head_swap:`, `FACE:`, and `ACTION:`: describe reference identity and source action without importing source identity traits. Inspect the guide panel and composed dimensions before rendering.

The retained author audio path requires mono or stereo audio in the source video. Normalize multichannel audio to stereo before use; the pinned video loader cannot interpret it correctly. The runner checks this before submission; silent-video support requires a separately tested adaptation. The initial range starts at frame 0 and loads at most 33 frames at 24 FPS; supply a prepared continuous segment with enough frames.

The prepared public sample uses a [NASA Christina Koch portrait](https://www3.nasa.gov/specials/artemis-ii/) and a 1.375-second shot from [Sintel](https://durian.blender.org/download/), © Blender Foundation, CC BY 3.0. YouTube extraction failed; the same film was obtained from Blender's official mirror. Hashes, crop/downmix details and the selected 118.25–119.625 second range are in `logs/input-preparation.json`. The actual 33-frame guide was checked with the installed nodes; its start/middle/end sheet is `logs/prepared-guide.png`. This human-to-animation test has directional-lighting and pose differences between inputs.

For API execution, set the manual prompt in the graph or pass `--prompt`. The runner uploads the inputs and waits for terminal ComfyUI history:

```bash
.venv/bin/python scripts/smoke-bfs.py \
  --video /path/to/source.mp4 --reference /path/to/reference.png \
  --workflow workflows/bfs-v3-rx9060xt-api.json \
  --url http://127.0.0.1:8189 --run-id my-smoke \
  --prompt 'head_swap: FACE: describe the reference identity. ACTION: describe the source action.' \
  --pid SERVER_PID --launch-settings './run-bfs.sh'
```

Replace `SERVER_PID` with the project's running ComfyUI process ID to sample process-tree memory. Use a unique run ID; a timeout or interruption stops observation and retains the prompt ID without cancelling the server job. The exact submitted graph, manifests, inputs and sampled memory observations are retained under `benchmarks/runs/`. The runner preserves server output metadata and copies the review artifact to `output/my-smoke.mp4`.

```bash
.venv/bin/python scripts/review-video.py --run-id my-smoke
ffprobe -v error -show_streams -show_format output/my-smoke.mp4
node scripts/playback-video.mjs --run-id my-smoke
```

Use [output review](.agent/skills/bfs-review-output/SKILL.md) to inspect decoded frames and video playback; contact sheets alone cannot establish temporal quality. The review tool checks the initial 640 × 320 composed output; pass explicit expected dimensions if a later candidate changes framing. Record observed guide-panel removal rather than assuming it. Preserve source audio explicitly when requested and verify its timing.

## Tested sample and limits

The following three rows are historical ROCm 7.2 observations.

| Run | Wall seconds | GPU GiB | Host RSS GiB | Process swap GiB |
| --- | ---: | ---: | ---: | ---: |
| bfs-smoke | 198.74 | 15.22 | 23.60 | 2.76 |
| bfs-lora08 | 172.57 | 15.25 | 22.58 | 7.53 |
| bfs-prompt-motion-retry | 234.60 | 15.31 | 21.12 | 4.15 |

On ROCm 10.0, the same frozen public-sample benchmark passed history, HTTP retrieval, 640 × 320 / 24 FPS / 33-frame metadata and full decoding. A [fresh process](benchmarks/optimization/rocm10-legacy-fresh/report.json) took 365.76 seconds. A [separate warm session](benchmarks/optimization/rocm10-legacy-warm/report.json) took 362.13 seconds for its excluded warmup, then 82.23 and 78.17 seconds with text/model cache reuse and all eight sampler steps executed. [Fresh](logs/playback-rocm10-legacy-fresh-baseline-1.json) and [final warm](logs/playback-rocm10-legacy-warm-baseline-3.json) browser playback completed with zero dropped/corrupted frames. These cache conditions differ from the historical single-run screening; they do not establish a repeatable upgrade speedup. Process swap and guide VAE out-of-memory fallback remain present. [Measurements and sampling limits](logs/rocm-10.0-upgrade/20261113T034906Z/measurements.json) are retained separately; inspected output remains similar to the historical sample and has no accepted quality improvement.

The author-aligned strength-1.0 sample has [ordered face frames](benchmarks/contact-sheets/bfs-smoke-all-face-frames.png). The earlier strength-1.0 and 0.8 output videos are no longer present in `output/`; their review records and contact sheets remain. Both removed the reference panel; the output recentered/filled the canvas, and the source's open mouth was suppressed. Lower strength weakened visible reference features without restoring the mouth expression. The prompt wording comparison also completed, but removing the reference closed-mouth phrase did not restore mouth opening. No candidate is a preferred quality preset. Submitted graphs and observations are retained in `benchmarks/runs/` and `benchmarks/results.jsonl`.

Sampled GPU peaks cover device 0, including other allocations; host peaks sum process-tree RSS and may double-count shared pages. Sampling uses a nominal two-second interval. They are observed peaks, not exact maxima. Reruns have different cache histories, so wall times and swap differences do not isolate a LoRA-strength effect.

In a later single fresh-server screening on the public sample, `legacy` took 513.736 seconds and `gpu-text` took 392.210 seconds, about 23.7% less ([baseline](benchmarks/optimization/opt-baseline-screen/report.json), [candidate](benchmarks/optimization/opt-gpu-text-screen/report.json)). The candidate had higher sampled process RSS and lower sampled process swap; regular guide VAE encoding ran out of memory and retried with tiled encoding. These are single observations with uncontrolled OS disk cache, not repeated medians or an accepted quality preset. The default remains `legacy`.

Repeated runs accumulated process swap. A `/free` request was followed by a queued-job stall; restarting only this project's server recovered execution. The failed queued attempt is retained as `bfs-prompt-motion`, separately from completed renders. Use a fresh project-server process between experiments when measuring resource use; the system `/opt/comfyui` service is outside this procedure.

The retained shot cuts after about 1.792 seconds, before a continuous 49- or 97-frame test could complete. Those gates need another continuous shot and a passing short-clip quality comparison. Larger precision/resolution candidates remain untested given the observed memory pressure. See `logs/duration-input-preparation.json`; 33 frames is an achieved workload, not a proven hardware maximum.

## Experiments and guidance

For controlled performance comparisons, stop the project UI after its jobs finish, then run:

```bash
.venv/bin/python -m unittest discover -s tests -p test_benchmark.py
.venv/bin/python scripts/benchmark-bfs.py --suite baseline
.venv/bin/python scripts/benchmark-bfs.py --suite memory --case gpu-text
```

The benchmark pins the public sample and baseline workflow hashes, caps a copy at 33 frames/24 FPS, and checks the completed video. Production workflows stay uncapped. `--session fresh` starts a server for each measurement. `--session warm --repeats 4 --case baseline` uses one server, excludes its first run as warmup, and attempts three further measurements; uniquely named, byte-identical video copies preserve the input hash while allowing the intended cache behavior. Warm mode does not force `--cache-none`. Cached samplers and diagnostic traces are excluded from performance medians. `--dry-run` shows inputs and launch commands without starting a server; `--trace --case baseline` runs a separate ROCm profiler diagnostic. Each invocation writes `benchmarks/optimization/<run-id-prefix>/report.json`, per-case server logs and WebSocket timelines, and the existing run ledger under `benchmarks/runs/`. Timelines measure client-observed node boundaries, not GPU kernel durations; the OS disk cache is uncontrolled.

The benchmark refuses an occupied port by default. `--external-server --pid SERVER_PID` explicitly observes an existing idle server, but cannot establish a fresh-process comparison or change its launch profile. A timeout, interruption or ambiguous submission retains the server and prompt evidence rather than cancelling a possibly active render. Inspect its queue/history before stopping that process. The `formats` suite reports its unmet model-validation prerequisites; native-format discovery metadata alone is not a tested candidate.

The installed ComfyUI checkout gates automatic AMD dynamic VRAM at HIP `(7, 14)`. The ROCm 10.0 framework reports HIP 7.15.26333, and explicit `./run-bfs.sh -- --enable-dynamic-vram` initializes comfy-aimdo on the RX 9060 XT ([startup evidence](logs/rocm-10.0-upgrade/20261113T034906Z/comfy-dynamic-clean-startup.txt)). This opt-in omits the launcher's default disable flag; the default remains `legacy`. The diagnostic completed successfully in ComfyUI history and wrote a fully decodable 33-frame artifact, but HTTP output retrieval timed out ([observer failure](benchmarks/runs/rocm10-dynamic-smoke/result.json)); later queue/history requests recovered. Dynamic VRAM remains experimental. Regular guide VAE encoding still needed an out-of-memory retry using tiles. When running `scripts/check-model-load.py`, give each guide diagnostic a unique `--report-dir` under `logs/` to preserve previous guides and reports.

Use [workflow tuning](.agent/skills/bfs-tune-workflow/SKILL.md) for fixed-input, fixed-seed comparisons with one changed factor and recorded failures. Use [ROCm debugging](.agent/skills/bfs-rocm-debug/SKILL.md) for failed gates. Results and observations belong in `benchmarks/`; sampled memory peaks are observations, not exact maxima.

Jobs above 33 frames, larger resolutions, rank64 or higher-precision comparisons, LTX-2.5, automatic captions, multi-pass refinement and service integration require separate evidence and remain deferred. The long-video runner keeps individual jobs at 33 frames; its full-movie endurance and quality remain unverified. See the [design](docs/superpowers/specs/2026-11-06-bfs-rocm-design.md), [implementation plan](docs/superpowers/plans/2026-11-06-bfs-rocm-implementation.md), and [project guidance](AGENTS.md) for acceptance gates and source links.
