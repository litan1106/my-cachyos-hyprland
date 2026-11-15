# ROCm 10 workload optimization execution

Execution started on 2026-11-14. This record distinguishes code verification,
successful execution, valid artifacts, quality findings, and performance evidence.
No production preset has been promoted.

The [manifest](../benchmarks/rocm10/manifest.json) and
[plan](superpowers/plans/2026-11-12-rocm10-workload-optimization.md) identify inputs,
source revisions, original-file backups, environments, and remaining gates.

## Environment and preflight

- RX 9060 XT, `gfx1200`, 16 GiB VRAM; device selection `HIP_VISIBLE_DEVICES=0`.
- Native SDK `/home/litan/.local/opt/rocm-10.0.0-gfx120X-all`.
- Python 3.12.13, PyTorch `2.13.0+rocm10.0.0`, reported HIP `7.15.26333`.
- Running kernel `7.3.4-1-cachyos`; installed LTS `6.18.60-2-cachyos-lts`.
- `uv lock --check`, `uv pip check`, discrete-device FP32/BF16 checks, and all
  six required BFS model size/hash checks passed. See
  [preflight evidence](../benchmarks/rocm10/preflight/commands.json).
- Native linkage resolves the selected SDK. PyTorch uses its matching virtual
  environment SDK wheel libraries; no global native library override is needed.
- BFS's frozen `versions.json` contains historical ROCm 7.2 metadata. Live
  package, server, and GPU-check records establish the actual ROCm 10 environment.

Use the project virtual environments. For experiments, select the native tools
and remove the inherited architecture override:

```bash
export ROCM_PATH=/home/litan/.local/opt/rocm-10.0.0-gfx120X-all
export HIP_PATH="$ROCM_PATH"
export PATH="$ROCM_PATH/bin:$PATH"
export HIP_VISIBLE_DEVICES=0
unset HSA_OVERRIDE_GFX_VERSION
```

## BFS evidence and limits

The frozen user-quality workload uses the selected portrait and 33 Sintel frames
at 24 FPS. Production workflow frame limits, models, V3 conditioning, LoRA,
prompt, seed, and sampling schedule remain unchanged.

| Attempt | Outcome | Observed wall seconds |
| --- | --- | ---: |
| fresh 1 | Successful history and artifact checks | 338.472 |
| fresh 2 | Exit 143; cause unknown; no performance result | — |
| fresh 2 retry | Successful history and artifact checks | 326.743 |
| fresh 3 | SDMA0 GPU mapping/protection fault before sampling progress | — |

These are fresh server processes with uncontrolled OS disk caches. Two valid
runs do not satisfy the planned three-run baseline. Warm measurements and a
profiler diagnostic remain pending. The failed attempt and retry are retained
in the [Task 2 summary](../benchmarks/rocm10/bfs/task2-summary.json).

Fresh 1's client-observed text-encoding nodes took 124.616 and 112.657 seconds;
the sampler took 77.226 seconds and tiled decoding 3.871 seconds. These are node
boundaries, not GPU kernel durations. Sampled process-tree RSS reached 27.04 GB
and swap 3.28 GB; samples do not establish exact maxima. This run did not log a
guide-VAE OOM retry. Historical fallback findings are separate evidence.

Startup selected PyTorch attention. Comfy-kitchen HIP and eager backends were
enabled and Triton disabled; availability does not identify each operator's
executed backend. Trace confirmation remains pending.

Root inspection of frames 0, 16, and 32 found a recognizable reference identity,
the guide panel absent, and broadly preserved scene/clothing. The source's open
mouth was reduced, especially in the middle/end frames, and facial proportions
were more stylized than the portrait. Playback and quality acceptance remain
separate gates. No preferred quality preset is established.

The fault occurred inside sampler node 382 after LTXAV model loading. Kernel
records identify the owned server process and SDMA0; no usable stack/coredump
identifies the exact call. Ordinary OOM is unproven. A post-fault FP32/BF16 device
check passed, which does not prove render stability. See
[fault diagnosis](../benchmarks/rocm10/bfs/fault-diagnosis.json).

The existing `offload-disabled` one-factor diagnostic also exited 143 during
CPU text processing, before it could test the GPU-fault hypothesis. Both owned
processes exited, with no usable result. See its
[retained interruption](../benchmarks/rocm10/bfs/offload-disabled-diagnostic.json).
Async transfer/pinning remains a hypothesis. Attention, Triton, and
compilation comparisons remain experimental while the baseline is unstable.

### Available commands

Run from `/home/litan/Projects/bfaceswap`, using the environment above and an
unoccupied loopback port 8189:

```bash
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite attention --dry-run
.venv/bin/python scripts/benchmark-bfs.py --config benchmarks/optimization/user-quality-config.json --suite memory --case offload-disabled --repeats 1 --run-id-prefix UNIQUE_ID
./run-bfs.sh --profile legacy
```

The matched attention profiles are `attention-sdpa`, `attention-split`,
`attention-quad`, and `attention-ck`; each retains legacy memory settings and
disables xformers. Launch construction now rejects conflicting attention flags
and inserts PyTorch attention only when none was selected. The unchanged default
is `legacy`. External Flash/Sage packages, dynamic VRAM, and native-FP8 rendering
have not been promoted. Inspect owned queue/history after ambiguous completion;
never terminate an unrelated server.

## Native llama.cpp

The existing HIP build settings were retained. `llama-server` was built with
`cmake --build build-rocm10 --target llama-server --parallel 4`. Binary hashes,
linkage, help, caches, and logs are in
[native build records](../benchmarks/rocm10/native-builds/llama.json).

All text benchmark results use Ornith 1.0 9B Q8_0, 9,527,500,992 bytes, SHA-256
`d0e4bebaa8b3450c62090df1408f2ee5ccb2094f9c610ffde564a654483d4f37`.
This is not the intended subtitle model. GPU offload and `gfx1200` enumeration
were confirmed in native logs.

| Workload | Mean tokens/s | Repetitions |
| --- | ---: | ---: |
| Prompt 128 | 1529.248 | 3 |
| Generation 32 | 31.728 | 3 |
| Prompt 2048 | 2666.338 | 3 |
| Prompt 2048 + generation 1024 combined | 93.361 | 3 |

The combined rate includes prompt tokens and must not be read as generation-only
throughput. These are baseline observations, not optimization improvements.
Exact commands, repetition samples, standard deviations, environment, hashes,
and two-second memory samples are retained in the
[short baseline](../benchmarks/rocm10/llama/20261114T183346.266769Z-baseline/run.json)
and [long workload](../benchmarks/rocm10/llama/20261114T183419.444391Z-translation/run.json).

From `/home/litan/Projects/my-cachyos-hyprland`, the captured runner executes one
case at a time and creates an exclusive run directory:

```bash
python3 benchmarks/rocm10/llama/run.py baseline
python3 benchmarks/rocm10/llama/run.py translation
python3 benchmarks/rocm10/llama/run.py flash
python3 benchmarks/rocm10/llama/run.py microbatch
python3 benchmarks/rocm10/llama/run.py kv
python3 benchmarks/rocm10/llama/run.py completion
python3 benchmarks/rocm10/llama/run.py server
```

The [flash comparison](../benchmarks/rocm10/llama/20261114T184107.820222Z-flash/run.json)
completed all six expected rows, three repetitions each, in 313.820 seconds:

| Flash setting | Prompt 2048 tokens/s | Combined prompt 2048 + generation 1024 tokens/s |
| --- | ---: | ---: |
| off | 2507.003 | 90.189 |
| on | 2654.000 | 93.307 |
| auto | 2648.648 | 93.218 |

On and auto are close in this invocation. These observations are restricted to
Ornith and this workload; no subtitle-model or general preset preference is
established. Raw repetition samples and standard deviations remain in its JSON.

Microbatch/KV tuning, deterministic completion, and server smoke gates are pending.
No GPU workload, compilation, or download may overlap a timed comparison.

## Whisper and subtitles

Whisper.cpp was cloned at tag `v1.9.5`, commit
`d1be6fde11ac6e0407606b4e42fe72d34add8037`, and `whisper-cli` built successfully in
`/home/litan/Projects/whisper_cpp/build-rocm10/bin/`. The build uses Release,
`GGML_HIP=ON`, `GPU_TARGETS=gfx1200`, the selected SDK HIP compiler/root, and
embedded SDK runtime paths. Exact configure/build commands, cache, help, hash,
and linkage are in [its build record](../benchmarks/rocm10/native-builds/whisper.json).
Pinned help confirms flash attention defaults on and supports `-fa`/`-nfa`.

The transcription wrapper preserves its existing CLI while correcting paths,
process-only environment, missing-asset/failure exit codes, dotted filenames,
validation, and atomic output publication. Invalid existing SRTs fail without
being overwritten. Its benchmark creates unique repeat directories and records
commands, duration, real-time factor, hashes, exits, and output eligibility.
The 60-second fixture conversion/source/hash is recorded in
`/home/litan/Learning/benchmarks/rocm10/config.json`; transcript accuracy remains
pending.

The translation wrapper defaults to the built `llama-completion`, sends a whole
multiline prompt with single-turn chat templating, bounds context/output, and
requires EOS. Opt-in loopback server mode uses independent chat requests with
prompt cache disabled. Every chunk must preserve all indices, timestamps, and
entry order before atomic final publication. Native verbose diagnostics retain
raw bytes so Japanese characters split across token pieces can be reconstructed.

The affected CPU suites passed: 5 runtime-profile, 22 BFS benchmark, 8
transcription, and 24 translation tests. See
[verification records](../benchmarks/rocm10/verification/checks.json).
Actual model rendering, GPU execution of subtitle tools, translation accuracy,
transcript review, and three-repeat model benchmarks remain pending.

### Model availability

The user deferred both model downloads. No Whisper model or Qwen shards were
downloaded, and Ornith was not substituted for subtitle translation. Required
assets remain `ggerganov/whisper.cpp`'s `ggml-large-v3-q5_0.bin` and all three
Q4_K_M shards from `Qwen/Qwen2.5-14B-Instruct-GGUF`.

A suggested future layout is permanent files under `~/Models/`, with recorded
revision/size/SHA-256 beside them and individual framework-location symlinks.
All Qwen shards must remain together with their original shard names. This
layout is advice; creating it and downloading the deferred models remain future
work. Hugging Face's [shared cache design](https://huggingface.co/docs/huggingface_hub/guides/manage-cache)
also uses revision snapshots linked to shared contents.

## Completion gates and rollback

Execution paused at the user's request on 2026-11-14 after the flash comparison
finished. No experiment-owned process remains and ports 8189/8190 are free. The
[resume checkpoint](../benchmarks/rocm10/RESUME.md) contains the next commands and
the [termination diagnosis](../benchmarks/rocm10/bfs/termination-diagnosis.json).

Task 1's environment freeze passed. Other task states remain tied to their
required execution, artifact, quality, and repeated-performance gates in the
companion task file. No overall speedup or preferred combined preset is claimed.
Select BFS's original `legacy` profile to retain the production default.
Translation retains its CLI path when `--server-url` is omitted and the baseline
35-layer setting when `--gpu-layers` is omitted. Original files and hashes are
retained in `benchmarks/rocm10/preflight/`; review their diffs before any selective
rollback so the user's prior changes remain intact.
