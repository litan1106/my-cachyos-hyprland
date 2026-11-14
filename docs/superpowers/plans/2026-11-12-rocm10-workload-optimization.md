# ROCm 10 workload optimization from AMD playbooks

Date: 2026-11-12 (revised 2026-11-14 after verifying it against the machine)

Status: In progress. Preflight passed; code and native build preparation started on 2026-11-14. The user deferred Qwen and Whisper model downloads, so their measurements remain pending. Execution evidence: `../../../benchmarks/rocm10/manifest.json`.

## Objective

Optimize BFS, ComfyUI, PyTorch, whisper.cpp transcription, and llama.cpp subtitle translation on the RX 9060 XT using relevant AMD playbook examples. Prioritize measured bottlenecks, existing runtime settings, compilation, and model reuse. Consider custom GPU kernels only after profiling identifies a worthwhile operator.

## Paths and references

The following aliases identify exact filesystem roots throughout this plan:

| Alias | Root | Version control |
| --- | --- | --- |
| B | `/home/litan/Projects/bfaceswap` | Not a Git repository; only its `ComfyUI` and custom-node checkouts are Git checkouts pinned in `versions.json` |
| L | `/home/litan/Projects/llama_cpp` | Git |
| S | `/home/litan/Learning` | Git, with existing uncommitted user changes |
| H | `/home/litan/Projects/my-cachyos-hyprland` | Git |
| W | `/home/litan/Projects/whisper_cpp` (proposed; no whisper.cpp installation exists) | Git checkout to be created |
| P | `/home/litan/Projects/playbooks/playbooks` | Reference only |

Read each project's applicable `AGENTS.md` (`B`, `L`, and `S` have one) before execution. For BFS, follow its local input-preparation, workflow-tuning, output-review, and ROCm-debugging procedures when applicable.

Relevant playbook sources:

- `P/core/comfyui-image-gen/README.md`, especially "Optimizing Attention for Performance" at line 583: attention selection and controlled comparisons.
- `P/supplemental/pytorch-kernels/README.md`: kernel compilation, extensions, and correctness examples.
- `P/core/pytorch-rocm-llms/README.md` and `assets/run_llm.py`: model loading and inference checks.
- `P/supplemental/clustering-rpc-server/README.md`: HIP builds and GPU detection; clustering is outside this single-machine plan.
- `P/supplemental/lemonade-getting-started/README.md` and `assets/lemonade_python_smoke.py`: persistent local serving and API interaction patterns.
- `P/supplemental/speech2speech-translation/assets/infer.py`: audio preprocessing and inference measurement patterns; this example uses SeamlessM4T, not Whisper.
- [AMD's attention-backend guide](https://rocm.blogs.amd.com/software-tools-optimization/comfyui-fa-backends/README.html).
- [whisper.cpp HIP build instructions](https://github.com/ggml-org/whisper.cpp#amd-rocm-gpu-support).

Adapt installation and architecture examples to CachyOS, ROCm 10.0, and `gfx1200`. Playbook examples are starting points, not evidence of compatibility or speedups on this machine. Backup speculative-decoding and GGUF-export playbooks are placeholders and are not dependencies.

## Starting evidence and constraints

Verified on 2026-11-14 unless noted otherwise.

- Hardware: RX 9060 XT with 16 GiB VRAM (`gfx1200`), 12 CPU threads, 30 GiB RAM, and 30 GiB swap. Running kernel `7.3.4-1-cachyos`; `6.18.60-2-cachyos-lts` is also installed.
- BFS uses Python 3.12.13, PyTorch `2.13.0+rocm10.0.0`, matching ROCm 10 SDK wheels, Triton `3.8.0+git4cff872c.rocm10.0.0`, and comfy-kitchen `0.2.41`.
- The native SDK prefix is `/home/litan/.local/opt/rocm-10.0.0-gfx120X-all`. The legacy `/opt/rocm` installation is absent. Preserve exact ROCm 10.0 rather than implicitly upgrading dependencies.
- BFS's benchmark runner has `baseline`, `memory`, `kernels`, and `formats` suites, and its `--suite` choices are hard-coded. The 21 existing `test_benchmark.py` tests pass. User-input baseline, warm-session, and compile-candidate dry runs passed their frozen input/workflow hash gates during planning. These dry runs did not execute rendering or prove compile-node compatibility.
- `scripts/bfs-runtime.py` always inserts `--use-pytorch-cross-attention`. The installed ComfyUI parser puts split, quad, PyTorch, Sage, Flash, and comfy-kitchen (`--use-ck-attention`) attention in one mutually exclusive group. Fix command construction before attention comparisons.
- The installed comfy-kitchen ships a HIP backend whose `architectures.json` lists `gfx1200` under RDNA4 WMMA, plus flash/sage attention modules. `--use-ck-attention` is therefore an installed candidate that needs no package upgrade. It is distinct from the Triton backend toggle (`--enable-triton-backend`).
- Prior BFS records show CPU text-processing time, swap pressure, and guide-VAE OOM/tiled retries. Output decoding is already tiled. Locate the actual failing encode stage before proposing another tiling change.
- `L/build-rocm10/bin` contains `llama-bench` and `llama-completion` only; `llama-server` and `llama-cli` are not built. The cache records Release, `GGML_HIP=ON`, `GPU_TARGETS=gfx1200`, `GGML_HIP_GRAPHS=ON`, `GGML_HIP_MMQ_MFMA=ON`, `GGML_HIP_NO_VMM=ON`, and `LLAMA_BUILD_SERVER=ON`, using the native SDK compiler. Do not present these existing settings as new optimizations.
- The only full GGUF model on the machine is the Ornith 1.0 9B Q8_0 benchmark model (9,527,500,992 bytes).
- `S/transcribe.py` (uncommitted user changes: 91 insertions, 79 deletions) invokes whisper.cpp. It sets `HSA_OVERRIDE_GFX_VERSION=12.0.0` and prepends `/opt/rocm/lib` at import time, and it exits 0 after a missing executable or failed subprocess. Its defaults (`~/whisper_cpp/build/bin/whisper-cli` and `~/whisper_cpp/models/ggml-large-v3-q5_0.bin`) do not exist. No `whisper-cli` binary or `ggml-*.bin` model exists anywhere under `/home/litan`, `/opt`, or `/usr/local`. `S/AGENTS.md` and dependencies still describe faster-whisper.
- `S/translate_srt.py` starts a subprocess per 50-entry chunk with `-ngl 35 -fa on -c 16384 -ctk q8_0 -ctv q8_0 -n -1 --simple-io`. Its executable default (`~/llama_cpp/build/bin/llama-cli`) and model default (`/home/li-tan/.cache/llama.cpp/Qwen_Qwen2.5-14B-Instruct-GGUF_qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf`, the first of three split shards) are both absent. In this llama.cpp revision, `llama-cli` is a chat front end built on the server; the non-interactive tool is `llama-completion`, which supports `--simple-io`, `--no-display-prompt`, `-cnv/-no-cnv`, and `-st`.
- `S` tracks 27 WAV/SRT files in Git and ignores only Python caches. Keep new fixtures and benchmark outputs unstaged.
- Preserve BFS's pinned upstream workflow, V3 persistent-reference conditioning, matching LTX-2.3 components, LoRA strength, sampling schedule, and uncapped production defaults. Change one factor per experiment.
- Keep project servers on loopback: BFS at `127.0.0.1:8189`, proposed translation server at `127.0.0.1:8190`. Refuse occupied ports; inspect queue/history before stopping an experiment-owned process after ambiguous completion. Leave `/opt/comfyui` and unrelated services untouched.
- Run GPU experiments sequentially. Do not overlap renders, transcription, translation, compilation, or model downloads with strict timing comparisons. Record cache conditions and remaining host activity.
- Keep failed runs and quality findings. Successful execution, valid artifacts, quality acceptance, and performance improvement are separate gates.
- Model downloads (whisper `ggml-large-v3-q5_0.bin`, about 1.1 GB; the Qwen2.5-14B Q4_K_M shards, about 9 GB) require the user's confirmation of source and location before they start.
- This plan does not authorize commits, pushes, or changes to unrelated projects. No Linux kernel customization is included.

## Task checklist

- [x] Task 1: Freeze the comparison environment.
- [ ] Task 2: Establish BFS baselines and locate the bottleneck.
- [ ] Task 3: Compare ComfyUI attention and memory settings.
- [ ] Task 4: Evaluate existing Triton and compilation candidates.
- [ ] Task 5: Tune the existing llama.cpp HIP build.
- [ ] Task 6: Restore and benchmark Whisper transcription.
- [ ] Task 7: Restore subtitle translation, then keep the model loaded across chunks.
- [ ] Task 8: Validate finalists and document usable presets.

The companion `.md.tasks.json` file tracks these same eight implementation tasks. Statuses record execution gates; model-dependent measurements remain pending after the user deferred downloads.

Execution order: Tasks 2→3→4 (BFS GPU), 5, 6, and 7 are independent after Task 1 but share the GPU, so run their measurements sequentially. Code and test work for Tasks 3, 6, and 7 can be done between timed runs, never during one.

### Task 1: Freeze the comparison environment

**Goal:** Every result identifies its inputs, software, model, and runtime settings.

**Files:** Create `H/benchmarks/rocm10/manifest.json` and `H/benchmarks/rocm10/preflight/`. Intended subtitle-translation and Whisper model locations are discovery items.

**Steps:**

1. Record source revisions, dirty-file status, Python/package versions, running and installed kernel versions, GPU identity, SDK version, and model hashes. Preserve existing changes to `S/transcribe.py` and unrelated work without reverting or staging it.
2. Save preflight evidence under `H/benchmarks/rocm10/preflight/`. For Git repositories (`S`, `L`, `H`), save `git status --porcelain`, `git rev-parse HEAD`, and `git diff` of every file this plan modifies. Because `B` is not a Git repository, copy each `B` file listed for modification in Tasks 3 and 8 into `preflight/B/`, preserving relative paths, and record their SHA-256 hashes. Task 8 diffs against these copies.
3. Select the verified native SDK through `ROCM_PATH` and `HIP_PATH`; put its tools on `PATH`. Set `HIP_VISIBLE_DEVICES=0`; remove an inherited `HSA_OVERRIDE_GFX_VERSION` from experiment processes unless a reproduced failure justifies it.
4. Preserve BFS's locked environment and verify that PyTorch loads its matching SDK wheel libraries. Check native linkage separately; do not globally inject native SDK libraries into every Python process.
5. Resolve the translation model. The stale default names llama.cpp's `-hf` cache file for `Qwen/Qwen2.5-14B-Instruct-GGUF`, `q4_k_m`, three split shards. Ask the user whether those shards exist elsewhere or should be downloaded. If downloading, pin the Hugging Face revision and record each shard's size and SHA-256. Do not silently substitute the Ornith benchmark model.
6. Resolve the Whisper model the same way: ask before downloading `ggml-large-v3-q5_0.bin` from `ggerganov/whisper.cpp` on Hugging Face, then pin its revision and SHA-256.
7. Record exact commands, sampling intervals, cache definitions, output directories, and unique run IDs in experiment manifests. Avoid overwriting prior run artifacts.

**Verify:** From `B`, with the selected SDK tools on `PATH` and no GFX override:

```bash
uv lock --check
uv pip check
HIP_VISIBLE_DEVICES=0 .venv/bin/python scripts/check-gpu.py
```

Require the discrete `gfx1200` device and finite FP32/BF16 results. Confirm that every `preflight/B/` copy matches its recorded hash. Record and resolve failures before that backend's GPU measurements. Missing Whisper or translation assets gate those branches (Tasks 6 and 7) without preventing BFS or llama.cpp measurements.

**Depends on:** None.

### Task 2: Establish BFS baselines and locate the bottleneck

**Goal:** Separate loading, CPU text processing, transfers, sampling, and VAE work.

**Files:** Reuse `B/benchmarks/optimization/user-quality-config.json`, `B/scripts/benchmark-bfs.py`, `B/benchmarks/runs/`, `B/benchmarks/results.jsonl`, and uniquely named output directories under `B/benchmarks/optimization/`.

**Steps:**

1. Verify the frozen source/reference/workflow hashes and model selection. Inspect prepared inputs and the composed guide before rendering.
2. Keep the prompt, seed, model family, quantization, V3 conditioning, LoRA strength, and sampling schedule fixed. Benchmark copies use 33 frames at 24 FPS; production workflows remain uncapped.
3. Measure three fresh-process runs and three eligible warm measurements. Record OS/model cache conditions without claiming fresh processes imply cold disk caches.
4. Collect one separate profiler diagnostic. Inspect node timelines, kernel/copy traces, sampled VRAM/RSS/swap, and guide-VAE fallback events. Client-observed node times are not GPU kernel durations.
5. Record which comfy-kitchen backends (`hip`, `triton`, `eager`) are active in the baseline server log and trace. Tasks 3 and 4 change this, so the baseline must state it.
6. Review decoded output, contact sheets, and actual playback. Scope quality findings to the evaluated inputs; the existing Sintel clip and selected portrait do not establish quality on every user video.

**Verify:** Run these commands sequentially from `B`, with port 8189 available:

```bash
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite baseline --repeats 3
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite baseline --case baseline --session warm --repeats 4
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite baseline --case baseline --trace --repeats 1
```

Warm mode excludes its first run. Exclude cached-sampler runs, diagnostics, and failed eligibility checks from performance medians. Require successful history, output retrieval, expected dimensions/FPS/frame count, full decoding, and documented frame/playback review. An observer timeout must retain queue/history and prompt evidence.

**Depends on:** Task 1.

### Task 3: Compare ComfyUI attention and memory settings

**Goal:** Identify settings that improve the measured BFS workload without changing models or conditioning.

**Files:** Modify `B/scripts/bfs-runtime.py`, `B/config/runtime-profiles.json`, `B/scripts/benchmark-bfs.py` (add `attention` to the `--suite` choices), `B/benchmarks/optimization/config.json`, `B/benchmarks/optimization/user-quality-config.json`, and `B/tests/test_benchmark.py`. Create `B/tests/test_runtime_profiles.py`.

**Steps:**

1. In `build_command`, select exactly one attention flag from the chosen profile and extra arguments. Add `--use-pytorch-cross-attention` only when none was supplied; reject conflicts before launching. Recognize all six flags in the installed attention group, including `--use-ck-attention`.
2. Add an `attention` suite and matched `attention-sdpa`, `attention-split`, `attention-quad`, and `attention-ck` profiles. Hold legacy memory settings constant and disable xformers consistently within this comparison. Preserve existing default behavior outside these opt-in profiles.
3. Confirm the effective backend using startup logs and representative traces; accepting a flag alone is insufficient. For `attention-ck`, confirm that comfy-kitchen's HIP attention kernels execute on `gfx1200` rather than falling back to eager, and apply the Task 2 quality gates before any speed comparison.
4. Screen existing memory cases individually: `gpu-text`, `offload-one`, `offload-disabled`, `no-pinned`, and `reserve-one`. Verify effective model placement rather than inferring it from profile names. With 16 GiB VRAM, `gpu-text` is expected to matter most for the measured CPU text-processing and swap cost; verify this rather than assuming it.
5. Repeat only promising candidates against matched controls. Measure a baseline before and after finalists to reveal drift.
6. Keep external Flash/Sage packages (`--use-flash-attention`, `--use-sage-attention`) behind a recorded `gfx1200`/ROCm 10 compatibility probe. Do not upgrade the production environment simply to try an attention package. Keep dynamic VRAM experimental while its output-retrieval behavior remains unresolved.

**Verify:** From `B`:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_runtime_profiles.py'
.venv/bin/python -m unittest discover -s tests -p 'test_benchmark.py'
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite attention --dry-run
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite memory --case gpu-text --repeats 1
```

Tests must reject conflicting selections and retain loopback binding, protected directories, safe process handling, and existing defaults. The 21 pre-existing `test_benchmark.py` tests must still pass. Apply Task 2's artifact and quality gates to candidate runs.

**Depends on:** Task 2.

### Task 4: Evaluate existing Triton and compilation candidates

**Goal:** Determine whether existing PyTorch optimization paths improve BFS.

**Files:** Reuse `B/scripts/benchmark-bfs.py`, the `kernels` suites in its optimization configs, `B/tests/test_benchmark.py`, and generated experiment graphs. Changes required by a reproduced compatibility failure are discovery items.

**Steps:**

1. Use the kernel playbook as the reference for compilation and correctness checks. Screen the existing `triton` and `compile` cases separately against their matched baseline.
2. Keep three things separate: comfy-kitchen's Triton backend (`--enable-triton-backend`), its HIP backend (Task 2's recorded state), and attention-backend selection (Task 3). Record which comfy-kitchen backend actually serves each operator.
3. Verify that `TorchCompileModel` registers and wraps the intended sampler model after LoRA application. Check actual kernel execution and compatibility with the selected GGUF model and offloading behavior. The `compile` case uses the `legacy` (`--lowvram`) profile, so partial offload and graph breaks are expected risks.
4. Measure compilation/startup cost separately from warm execution. Record recompilations, memory growth, fallback behavior, and failures; repeat in a second fresh process to characterize cache reuse.
5. Retain working eager execution as the fallback. Propose a separate custom HIP/Triton operator design only if profiling still identifies a substantial bottleneck with a testable reference implementation. Tutorial vector-add or naive matmul speed is not an application speedup.

**Verify:** From `B`, first run each case once in a fresh process. For successful cases, collect warm measurements:

```bash
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite kernels --case compile --session fresh --repeats 1
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite kernels --case compile --session warm --repeats 4
```

Repeat with `--case triton`, keeping other settings fixed. Require Task 2's execution, artifact, and quality gates. If compilation changes fail, run the relevant benchmark tests before another workload attempt.

**Depends on:** Tasks 2 and 3.

### Task 5: Tune the existing llama.cpp HIP build

**Goal:** Improve prompt processing and generation using supported runtime settings, and build the server Task 7 needs.

**Files:** Reuse `L/build-rocm10/`. Create results under `H/benchmarks/rocm10/llama/` and reference them from `H/benchmarks/rocm10/manifest.json`.

**Steps:**

1. Use the exact cached Ornith Q8_0 model recorded in `B/logs/rocm-10.0-upgrade/20261113T034906Z/llama-workload.json`. Verify its existence, size (9,527,500,992 bytes), and SHA-256 (`d0e4beba…4f37`). Record this as the text benchmark model, separately from the intended subtitle-translation model.
2. Establish the existing `-p 128 -n 32 -r 3 -ngl 999 -o json` baseline. Keep the normal benchmark warmup and record it.
3. Add a translation-shaped workload: `-p 2048` for prompt processing and `-pg 2048,1024` for a long prompt followed by long generation. The benchmark sizes context from its test workload; do not pass a serving-only context option to `llama-bench`.
4. Change one factor per invocation, using `llama-bench`'s comma-separated values so each factor's candidates share one process and warmup:
   - Flash attention: `-fa off,on,auto`.
   - Microbatch: `-ub 256,512,1024,2048` with `-b 2048` fixed.
   - KV cache type: `-ctk f16,q8_0 -ctv f16,q8_0` with flash attention on. The translation script uses `q8_0`; quantized V cache requires flash attention.
   - Threads: `-t 4,6,12`. Run last, and only if earlier results or the trace show CPU time at full offload.
   Avoid a Cartesian product of all options.
5. Preserve source revision, model, and quantization throughout comparisons. Record prompt tokens/s, generation tokens/s, load time, memory observations, and deterministic output.
6. Build the server for Task 7 from `L` without changing the source or build configuration: `cmake --build build-rocm10 --target llama-server --parallel 4`. Record the resulting binary hash and linkage.

**Verify:** Recheck installed `llama-bench --help`, `llama-completion --help`, and `llama-server --help`; compare repeated JSON results. Run the recorded completion probe with `llama-completion -no-cnv`, prompt `The capital of France is`, seed 42, and temperature zero. Confirm HIP offload on the discrete GPU and linkage to the intended SDK for all three binaries. A successful benchmark does not validate an untested server.

**Depends on:** Task 1.

### Task 6: Restore and benchmark Whisper transcription

**Goal:** Make the actual whisper.cpp pipeline reproducible on ROCm 10, then tune it.

**Files:** Create `W` (no installation exists). Modify `S/transcribe.py` and `S/AGENTS.md`. Create `S/tests/test_transcribe.py`, `S/benchmarks/rocm10/config.json`, `S/scripts/benchmark-transcribe.py`, and fixture/output directories under `S/benchmarks/rocm10/`.

**Steps:**

1. Clone whisper.cpp into `W` at a pinned release tag and record the commit. Use the model resolved in Task 1, step 6. Do not silently switch transcription frameworks.
2. Build `whisper-cli` in `W/build-rocm10/` with Release mode, `GGML_HIP=ON`, and `GPU_TARGETS=gfx1200`, matching the variable in `L`'s cache; current ggml deprecates `AMDGPU_TARGETS`. Select the verified SDK compiler (`$ROCM_PATH/lib/llvm/bin/clang`, as in `L`) and root explicitly, and embed its library runtime paths. Build with `--parallel 4`; check the resulting cache and linkage.
3. Preserve the user's current script changes. Move the import-time `os.environ` mutation into a function that builds a process-scoped ROCm 10 environment for the subprocess only, with no GFX override and no `/opt/rocm` path. This also lets tests import the module without side effects. Update executable/model defaults to the `W` paths while keeping explicit CLI overrides.
4. Add executable/model preflight checks before any file is processed. Exit nonzero when the executable or model is missing or any file fails; the current script exits 0 in both cases. Correct contradictory backend/setup statements in `S/AGENTS.md`; do not restore its old ROCm 7.2 installation recipe or remove dependencies without first checking their actual consumers.
5. Prepare `S/benchmarks/rocm10/fixtures/ja-60s.wav` from one existing Japanese recording under `S/Hono/` or `S/Yu/`. Record the exact source, range, hash, and 16-kHz mono PCM conversion in the config. Retain originals and leave the fixture unstaged. Create a reviewed reference transcript or mark accuracy acceptance pending.
6. Implement a small benchmark script that calls the existing transcriber, records wall time, audio duration, real-time factor, process status, model/binary hashes, and output checks. Use a unique output directory for every repeat: the current transcriber skips existing SRTs.
7. Compare threads `2/4/8` with the same model, language, decoding parameters, and audio. Read the pinned binary's `--help` for its flash-attention default and toggle, then compare on and off. Treat smaller models, different quantization, and beam/best-of changes as separate quality experiments.

**Verify:** From `S`, run `.venv/bin/python -m unittest discover -s tests -p 'test_transcribe.py'`. Cover missing executable/model, failed subprocesses (nonzero exit), skipped-output detection, and absence of `HSA_OVERRIDE_GFX_VERSION` and `/opt/rocm` in the subprocess environment. The benchmark script must document its exact CLI via `--help` and write all actual commands to its report. Require three measured repetitions, confirmed HIP offload, valid SRT timestamps, and transcript review; inability to run the old broken defaults is not a speedup baseline.

**Depends on:** Task 1 (model resolved and download approved).

### Task 7: Restore subtitle translation, then keep the model loaded across chunks

**Goal:** Restore a working CLI baseline, then measure full GPU offload and persistent llama.cpp serving as separate factors.

**Files:** Modify `S/translate_srt.py`. Create `S/tests/test_translate_srt.py` and `S/benchmarks/rocm10/translation-config.json`. Store comparison artifacts under `S/benchmarks/rocm10/translation/`.

**Steps:**

1. Repair executable/model configuration using Task 1's verified assets. Replace the absent `llama-cli` default with `L/build-rocm10/bin/llama-completion`, and remove the unconditional `HSA_OVERRIDE_GFX_VERSION`. Preserve current CLI arguments and explicit overrides.
2. Fix the prompt format before measuring. `llama-completion -no-cnv` sends raw text without the chat template, which changes model behavior for an Instruct model. Use single-turn chat (`-cnv -st`) with the whole multi-line prompt passed through `-f <file>` or `-p`, not stdin, because interactive input ends a turn at a newline. Confirm with `--verbose-prompt` that the chat template wraps the entire prompt, and record the rendered prompt.
3. Establish the CLI baseline with the existing settings (`-ngl 35 -fa on -c 16384 -ctk q8_0 -ctv q8_0`). Then change one factor: `-ngl 999`. The Q4_K_M 14B weights (about 9 GB) plus a 16k `q8_0` KV cache should fit in 16 GiB; confirm with measured VRAM, not this estimate.
4. Add an opt-in `--server-url` mode using one local `llama-server` at `127.0.0.1:8190` with `-np 1` and the same model, context, offload, KV cache precision, and generation settings as the winning CLI configuration. Use the OpenAI-compatible chat endpoint so the same chat template applies. No native source changes are planned.
5. Keep the model loaded across chunks. Send independent requests without carrying preceding subtitle content into later prompts. Keep prompt-cache optimization separate from the initial process-reuse comparison.
6. Check input and output token budgets against context limits. Detect truncation and unsuccessful responses rather than publishing incomplete translations.
7. Require exactly one translated entry per input subtitle with unchanged timestamps and order. Reject missing/duplicated entries, malformed responses, and failed chunks. Publish the final SRT atomically only when the entire file passes validation.
8. Retain the CLI route as a fallback. Keep the experiment server process owned and recorded; do not terminate an unrelated service. Do not concurrently benchmark translation and BFS.

**Verify:** From `S`, run `.venv/bin/python -m unittest discover -s tests -p 'test_translate_srt.py'`. Cover malformed responses, omitted/duplicated entries, timestamp changes, context/truncation failures, and server failures without partial final publication. Compare three runs each of the CLI baseline, full-offload CLI, and server mode on the same multi-chunk fixture; record server startup separately from subsequent requests. Review translation quality before preferring a mode.

**Depends on:** Task 1 (translation model resolved and download approved) and Task 5 (`llama-server` built).

### Task 8: Validate finalists and document usable presets

**Goal:** Produce reproducible settings with explicit benefits, limits, and rollback commands.

**Files:** Update `B/README.md`, `B/TUNING_GUIDE.md`, `S/AGENTS.md`, and `H/docs/rocm-install-arch.md`. Create `H/docs/rocm10-workload-optimization.md`. Update the task checklist and companion task statuses to reflect achieved gates.

**Steps:**

1. Repeat finalists with matched inputs, models, versions, and cache definitions. Use three fresh BFS measurements and four warm-session runs, with the first warm run excluded, where applicable. Repeat native/audio benchmarks at least three times.
2. Report runtime distributions, sampled memory observations, failures, and quality findings. Keep cold/startup, warm, diagnostic, and cached-node results distinguishable. Do not attribute changes to ROCm when source versions, inputs, or settings differ.
3. Test combined winning settings separately; individual improvements may interact. Preserve unchanged production presets until this combined check passes.
4. Prefer a candidate only for repeatable improvements beyond observed run variation, or demonstrated OOM recovery at the same workload, with accepted output quality. Restrict claims to evaluated inputs and settings. Broader user-video quality needs representative user clips and review.
5. Document exact launch commands, environments, model checksums, output/review records, and commands to select original presets. Mark unresolved candidates experimental. Do not promote the optional native-FP8 format or dynamic-VRAM paths without their separate compatibility and quality gates.
6. Change defaults only after recording the evidence and acceptance scope. Keep successful execution, artifact validity, accepted quality, and performance improvement separately stated.

**Verify:** Run affected unit suites in `B` and `S`, BFS metadata/full-decode/playback checks, and transcription and translation reviews. Run `git diff --check` in `S` and `H`. For `B`, which has no Git, run `diff -u` between each `H/benchmarks/rocm10/preflight/B/` copy and the current file, and check the output for trailing whitespace. Inspect all diffs for unrelated changes and confirm that no fixture, model, or output file is staged in `S`. Every documented command must identify the tested environment, and every performance claim must link to retained measurements. A task with unresolved required gates remains pending or in progress rather than completed.

**Depends on:** Tasks 3, 4, 5, 6, and 7.
