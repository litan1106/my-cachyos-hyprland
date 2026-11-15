# Resume ROCm 10 workload optimization

The user requested a pause on 2026-11-14, to resume tomorrow. Do not restart work
until the user resumes it. No commits, pushes, staging, or branch operations were
authorized. Preserve the pre-existing changes in `/home/litan/Learning`.

## Read first

- [Execution report](../../docs/rocm10-workload-optimization.md).
- [Manifest](manifest.json), [plan](../../docs/superpowers/plans/2026-11-12-rocm10-workload-optimization.md),
  and its companion `.md.tasks.json`.
- [BFS measurements/failures](bfs/task2-summary.json),
  [GPU diagnosis](bfs/fault-diagnosis.json), and
  [offload-disabled interruption](bfs/offload-disabled-diagnostic.json).
- Applicable repository `AGENTS.md` and the subagent development skill.

The last invocation completed successfully before the pause:
[`20261114T184107.820222Z-flash`](llama/20261114T184107.820222Z-flash/run.json),
exit 0, all six expected rows present, three repetitions per setting/workload.
No experiment-owned process remains; loopback ports 8189 and 8190 are free.
No warm BFS, trace, microbatch, KV, completion, or server run was started afterward.

## What is done

- Task 1: original files/backups, source and dirty-status records, environments,
  model hashes, and preflight checks saved. GPU finite FP32/BF16 and six required
  BFS model checks passed.
- Task 3 code: attention conflict handling, four matched attention profiles,
  configs and tests implemented. Production `legacy` default unchanged.
- Task 5: built `llama-server` without source/config changes. Ornith short and
  long baseline cases and the flash comparison passed.
- Task 6 code/build: whisper.cpp v1.9.5 commit
  `d1be6fde11ac6e0407606b4e42fe72d34add8037` built with HIP `gfx1200` and SDK rpaths.
  Transcriber, tests, unique-output benchmark harness, and 60-second fixture are
  ready. Output is validated before atomic publication; invalid existing SRTs
  fail without being overwritten.
- Task 7 code: corrected single-turn CLI chat, opt-in loopback server mode,
  context/EOS/truncation checks, exact SRT structure validation, atomic output,
  raw verbose-diagnostic bytes and prompt reconstruction. Synthetic fixture and
  experiment config saved.
- Independent review found and corrected partial Whisper publication and
  Japanese UTF-8 diagnostic handling. Fresh root verification passed all 59
  affected CPU tests: 5 runtime + 22 BFS benchmark + 8 transcription + 24
  translation. Evidence: [verification](verification/checks.json).
- Task 8 documentation reflects achieved gates and failures. No preferred
  preset, combined-setting validation, or overall speedup claim was made.

## BFS: investigate before comparisons

Two fresh runs passed in 338.472 and 326.743 seconds. Fresh 2 originally exited
143; its retry succeeded. Fresh 3 hit a kernel-confirmed SDMA0 GPU mapping/
protection fault at sampler node 382 after LTXAV load, before sampling progress.
The `offload-disabled` diagnostic also exited 143 during CPU text processing,
before testing the GPU-fault hypothesis. All failed records remain retained.

The [termination diagnosis](bfs/termination-diagnosis.json) retains exact launch
and poll timing; no fixed timeout, RTK cause, or signal sender was established.
The SIGTERM sender and GPU-fault exact call are unknown. Do not conflate the two
failures. A post-fault device check passed, and native Ornith workloads passed,
but neither establishes BFS render stability. Ordinary OOM was not established.
Async transfer/pinning remains an unconfirmed hypothesis.

Task 2 does not have three valid fresh runs, warm measurements, a trace, or
technical playback. Tasks 3/4 effective-backend and performance comparisons are
pending. Only startup backend availability is known: PyTorch attention, HIP and
eager enabled, Triton disabled. Trace actual operator execution before claims.

Root inspected baseline frames 0/16/32: identity recognizable, no guide panel,
scene/clothing broadly retained; source mouth opening reduced and facial
proportions stylized. Playback/quality acceptance remains pending.

First fresh run's two text nodes consumed about 237 seconds; sampler about 77
seconds. These are client-observed node durations. No guide-VAE OOM fallback
appeared in that run. Keep historical tiling findings separate.

Before another render, inspect termination diagnosis and use recorded process
ownership/prompt evidence. A direct root-controlled invocation with early PID,
cgroup and signal-lifecycle capture may distinguish control-path termination
from runtime failure. Do not guess at a source fix, upgrade dependencies, set a
GFX override, reboot, or stop unrelated services. Do not promote a workaround
from one successful diagnostic.

## Native llama.cpp: remaining work

Runner: `python3 benchmarks/rocm10/llama/run.py CASE`, run from
`/home/litan/Projects/my-cachyos-hyprland`. Each case uses the verified 9.5 GB
Ornith Q8_0 model and writes unique timestamped evidence under `llama/`.

Remaining cases after the flash comparison: `microbatch`, `kv`, `completion`,
and `server`. Inspect each result before the next. Run threads only if evidence
shows a CPU bottleneck; sampled native GPU utilization was 100% in the long case.
The native server smoke is an Ornith test, not Qwen subtitle validation. Keep
server on `127.0.0.1:8190`, refuse an occupied port, and stop only the owned PID.

Short baseline: prompt 128 = 1529.248 tokens/s, generation 32 = 31.728 tokens/s,
three internal repeats. Long baseline: prompt 2048 = 2666.338 tokens/s; combined
prompt 2048 + generation 1024 = 93.361 tokens/s. Combined throughput is not
generation-only speed. Source/model/quantization remain fixed; no ROCm speedup
can be inferred from unrelated historical records.

The completed long-workload flash comparison observed prompt rates 2507.003 /
2654.000 / 2648.648 tokens/s for off/on/auto, and combined prompt+generation rates
90.189 / 93.307 / 93.218 tokens/s. Auto and on are close in this invocation;
do not promote a general preset or claim subtitle-model speedups from it.

## Models remain deferred

The user explicitly deferred both model downloads. Do not download without a
new instruction. Missing assets gate real Task 6/7 measurements and quality:

- `ggerganov/whisper.cpp`, `ggml-large-v3-q5_0.bin` (~1.1 GB).
- `Qwen/Qwen2.5-14B-Instruct-GGUF`, Q4_K_M, all three shards (~9 GB).

The user asked whether permanent home-directory files with framework symlinks
would be sensible. Root recommended `~/Models/` with pinned revisions/hashes and
individual links; all Qwen shards must stay siblings with original names. This
was advice, not approval to download or a completed migration. No `~/Models/`
layout or model links were created. Do not substitute Ornith for subtitle tests.

Current expected defaults:

- Whisper executable: `/home/litan/Projects/whisper_cpp/build-rocm10/bin/whisper-cli`.
- Whisper model: `/home/litan/Projects/whisper_cpp/models/ggml-large-v3-q5_0.bin`.
- Translation executable: `/home/litan/Projects/llama_cpp/build-rocm10/bin/llama-completion`.
- Translation model: `/home/litan/.cache/llama.cpp/Qwen_Qwen2.5-14B-Instruct-GGUF_qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf`.

## Environment and verification

```bash
export ROCM_PATH=/home/litan/.local/opt/rocm-10.0.0-gfx120X-all
export HIP_PATH="$ROCM_PATH"
export PATH="$ROCM_PATH/bin:$PATH"
export HIP_VISIBLE_DEVICES=0
unset HSA_OVERRIDE_GFX_VERSION
```

Use project virtual environments. PyTorch uses matching SDK wheel libraries;
native binaries carry SDK rpaths. Do not globally inject native libraries into
Python. Runtime is ROCm 10 although frozen BFS `versions.json` includes stale
ROCm 7.2 descriptive metadata.

Run GPU workloads sequentially. Do not overlap them with compilation, model
downloads, or code/test work during strict measurements. Keep unique run IDs,
retained failures, exact commands, cache conditions, and two-second sampling.
Fresh processes do not imply cold disk caches. No final video-quality preference
is accepted from frame sheets alone.

After actual code changes, rerun affected suites, inspect B diffs against
`preflight/B/`, run `git diff --check` in H/S, and confirm no fixture/model/output
was staged. Existing successful test evidence does not validate real missing
models or render stability. Mark tasks complete only when their required gates
have passed.
