# ROCm 10 on CachyOS with llama.cpp and BFS

[Documentation index](README.md) · [Historical llama.cpp ROCm 7.2 guide](llama_rocm-install-arch.md)

Local evidence links below point to files on the recorded machine and may not resolve elsewhere. Tested 2026-11-12 on an RX 9060 XT (`gfx1200`). Evidence is in [the upgrade logs](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z). The running kernel was `7.3.3-1-cachyos`, while `7.3.4` was installed; no reboot or driver change was made.

AMD's [ROCm 10.0 installation instructions](https://rocm.docs.amd.com/en/docs-10.0.0/install/rocm.html), [TheRock transition guide](https://rocm.docs.amd.com/en/docs-10.0.0/about/transition-guide-TheRock.html), and [PyTorch installation guide](https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html) are the primary references. CachyOS is outside AMD's [ROCm 10.0 supported distribution list](https://rocm.docs.amd.com/en/docs-10.0.0/about/release-notes.html#operating-system-support); this record demonstrates local feasibility only.

## User-local SDK and device check

The enabled repositories did not offer exact ROCm 10.0: stable offered 7.2 and testing 10.1. Instead, the AMD `gfx120X-all` 10.0.0 tarball was installed under `/home/litan/.local/opt/rocm-10.0.0-gfx120X-all`. The initial SDK install did not modify pacman packages or require root. At the user's subsequent request, the complete 44-package ROCm 7.2 dependency closure was removed with a dependency-checked `pacman -R` transaction; `/opt/rocm` and its old package-owned loader/profile settings are now absent. Repositories and system GPU drivers were not changed. The two unowned Python bytecode remnants were inspected and removed separately.

The archive was [AMD's ROCm 10.0.0 distribution](https://stable.repo.amd.com/rocm/core/tarball/therock-dist-linux-gfx120X-all-10.0.0.tar.gz). Its source metadata, CRC and ETag verification passed; see [archive.verification.json](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/archive.verification.json). The archive was 2,423,376,158 bytes and expanded files totaled 9,864,360,479 bytes. The SHA-256 computed locally after verification was `eb99db434a1738fd83b0c3b933146cdb76418f35fcf4647743fbdfef76e8c71f`; it is not an AMD-published checksum.

To reproduce the verified archive locally, download it and compare it to the locally pinned hash above, then extract its root directly into a fresh prefix. The hash checks for identical bytes to the archive verified in this run; it is not an independent AMD signature. The `mkdir` fails if the target already exists, preserving the existing installation.

```bash
archive=therock-dist-linux-gfx120X-all-10.0.0.tar.gz
curl -fL -o "$archive" "https://stable.repo.amd.com/rocm/core/tarball/$archive" &&
  printf '%s  %s\n' eb99db434a1738fd83b0c3b933146cdb76418f35fcf4647743fbdfef76e8c71f "$archive" | sha256sum -c - &&
  mkdir -p "$HOME/.local/opt" &&
  mkdir "$HOME/.local/opt/rocm-10.0.0-gfx120X-all" &&
  tar -xzf "$archive" -C "$HOME/.local/opt/rocm-10.0.0-gfx120X-all"
```

For native SDK commands, select both paths explicitly. A bare `hipconfig` can resolve the older `/opt/rocm` installation. `.info/version` identifies the SDK release; its HIP component reports `7.15.26333` and its compiler is AMD Clang 23.0.0git.

```bash
export ROCM_PATH=/home/litan/.local/opt/rocm-10.0.0-gfx120X-all
export HIP_PATH="$ROCM_PATH"
export LD_LIBRARY_PATH="$ROCM_PATH/lib:$ROCM_PATH/lib/llvm/lib"
export HIP_VISIBLE_DEVICES=0
unset HSA_OVERRIDE_GFX_VERSION
cat "$ROCM_PATH/.info/version"
"$ROCM_PATH/bin/hipconfig" --version
```

With those library paths, the native probe's dependencies resolved to this SDK rather than ROCm 7.2; see [ldd output](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/hip-probe-ldd.txt). `"$ROCM_PATH/bin/amd-smi" list` identified device 0 as the discrete GPU, corroborated by `"$ROCM_PATH/bin/rocminfo"`. The [native HIP probe source](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/hip-probe.cpp) produced 1,024 finite FP32 results matching its CPU reference on RX 9060 XT, PCI `0000:03:00.0`, without an ISA override; see [probe output](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/hip-probe-run.txt).

With the environment above, rebuild and run the recorded probe as follows. `ldd` should resolve ROCm libraries to the selected SDK.

```bash
probe_dir=/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z
"$ROCM_PATH/bin/hipcc" --offload-arch=gfx1200 "$probe_dir/hip-probe.cpp" -o /tmp/bfs-rocm10-guide-probe
ldd /tmp/bfs-rocm10-guide-probe
/tmp/bfs-rocm10-guide-probe
```

## Legacy SDK removal

The removal transaction includes the system `python-pytorch-rocm`, `python-onnxruntime-rocm` and `python-aotriton` integrations because they depend on the legacy SDK. The BFS `.venv`, ROCm 10 archive install, cached recovery archives and model files were retained. No recursive orphan removal or forced dependency bypass was used. The reviewed [transaction script](/home/litan/Projects/bfaceswap/logs/rocm-7.2-removal/20261113T043533Z/remove-rocm72.sh) checks every installed version before removing only the named packages; [execution output](/home/litan/Projects/bfaceswap/logs/rocm-7.2-removal/20261113T043533Z/removal.txt) records its completion. The package manager's normal snapshot and linker-cache hooks ran.

The BFS launcher and installer now default to `$HOME/.local/opt/rocm-10.0.0-gfx120X-all`, set `HIP_PATH` to the selected `ROCM_PATH`, and put that SDK's tools first on `PATH`. The benchmark uses the same selection for monitoring and `rocprofv3`. The SDK's own `rocm-smi` compatibility tool was verified with the expected JSON schema; it does not require the removed monitoring package. Explicit `ROCM_PATH` overrides remain supported. Existing processes may retain an old environment; open a new terminal for the updated `~/.bashrc` exports.

After uninstalling 7.2, the native HIP arithmetic probe, BFS installer check with the SDK selected by defaults, finite FP32/BF16 checks, llama.cpp GPU text inference and all 60 unit tests passed. This supersedes the earlier side-by-side state while preserving its measurement records. The final short post-removal render is recorded separately.

## BFS environment

BFS's production `pyproject.toml` and `uv.lock` were updated and `uv sync --locked` completed in `/home/litan/Projects/bfaceswap`. Python remained 3.12.13. The locked environment uses PyTorch `2.13.0+rocm10.0.0`, torchvision `0.28.0+rocm10.0.0`, torchaudio `2.11.0.2+rocm10.0.0`, and Triton `3.8.0+git4cff872c.rocm10.0.0`, with exact ROCm 10.0.0 SDK and gfx1200 device packages. The AMD wheel index and direct transitive source mappings are explicit in the project configuration.

`uv lock --check`, `uv pip check`, GPU FP32 and BF16 calculations, and torchvision and torchaudio import/operation checks passed. The Python process loaded ROCm libraries from the virtual environment's `_rocm_sdk_core` and `_rocm_sdk_libraries`, not `/opt/rocm`; see [framework evidence](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/framework-after.txt) and [GPU checks](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/bfs-gpu-after.txt). ComfyUI startup and registration of the 32-node graph passed. The corrected launcher and installer honor an explicit `ROCM_PATH`; the launcher removes `--disable-dynamic-vram` when explicitly passed `--enable-dynamic-vram`. The default remains legacy VRAM. A [clean startup](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/comfy-dynamic-clean-startup.txt) initialized aimdo with Dynamic VRAM enabled and no contradictory flag warning; [server stats](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/comfy-dynamic-clean-stats.json) record the arguments.

The dynamic diagnostic logged graph execution in 326.55 seconds and wrote a 640 x 320, 24 FPS, 33-frame video that fully decoded. Its saved ComfyUI history confirms successful completion. The observer then failed with a 30-second HTTP timeout downloading `/view`; later queue/history checks recovered and confirmed an empty queue. This passes the graph/history gate but exposes an output-retrieval failure. The raw artifact, failed run record and [stop evidence](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/dynamic-stop-record.json) were retained before stopping only that diagnostic server. The guide VAE still exhausted memory and retried tiled encoding. This diagnostic overlapped native compilation and is excluded from performance comparisons; dynamic VRAM is not a validated default.

To restore the prior BFS environment, copy the saved `pyproject.toml.before` and `uv.lock.before` from the upgrade log directory over the project files and run `uv sync --locked` in the BFS project without the custom SDK `LD_LIBRARY_PATH`. The old native setup also requires reinstalling its removed SDK packages before selecting `/opt/rocm`; changing only the Python lockfiles does not restore the system stack. All 44 exact package versions and original install reasons are recorded in [the removal manifest](/home/litan/Projects/bfaceswap/logs/rocm-7.2-removal/20261113T043533Z/removal-manifest.json), with verified existing cached archive paths in [the recovery list](/home/litan/Projects/bfaceswap/logs/rocm-7.2-removal/20261113T043533Z/cached-recovery-archives.txt). A requested rollback would reinstall those archives with `pacman -U` and restore the recorded install reasons and matching environment. Rollback was prepared, not executed. Keep the recorded artifacts.

## BFS measurements and remaining limits

The fixed public-sample legacy render passed ComfyUI history, HTTP video retrieval, 640 x 320 / 24 FPS / 33-frame metadata and full-frame decoding. It used the frozen prompt, seed `1035625245488400`, Q3 LTX-2.3 transformer, Q4 Gemma and adaptive V3 LoRA at strength 1.0. The [fresh-process report](/home/litan/Projects/bfaceswap/benchmarks/optimization/rocm10-legacy-fresh/report.json) records 365.76 seconds; the historical 7.2 screening recorded 513.74 seconds. The new process followed kernel probes and the dynamic render, so first-use caches were already exercised. The historical cache state and host workload were not matched. These single observations do not establish a repeatable upgrade speedup.

The new run sampled 15.77 GiB device VRAM, 21.97 GiB process-tree RSS and 3.71 GiB process swap. Its first sampling iteration was 14.98 seconds in the server progress log; subsequent client progress intervals averaged 8.42 seconds. The client interval from sampler-node entry to step 1 was 28.38 seconds, including model preparation. CPU text nodes consumed 244.92 seconds. Device VRAM includes other allocations, process-tree RSS can double-count shared pages, and nominal two-second samples can miss peaks. Client timings are not GPU kernel timings. The [measurement record](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/measurements.json) retains these definitions and historical values separately.

With the SDK environment above, the measured fresh command and separate warm-session command are:

```bash
cd /home/litan/Projects/bfaceswap
.venv/bin/python scripts/benchmark-bfs.py --suite baseline --session fresh --repeats 1 \
  --run-id-prefix rocm10-legacy-fresh --timeout 900
.venv/bin/python scripts/benchmark-bfs.py --suite baseline --session warm --repeats 3 \
  --run-id-prefix rocm10-legacy-warm --baseline-run-id rocm10-legacy-fresh-baseline-1 --timeout 900
```

Run IDs above identify retained records; choose new IDs to rerun. The warm session completed all three jobs successfully, with its first run excluded as warmup. The next two runs both executed all eight sampler steps and passed history, HTTP retrieval, metadata and full decoding. Cached text/model reuse shortened their runtime; regular guide VAE encoding retried with tiles on both measured warm runs.

| ROCm 10 legacy session | Wall seconds | Sampled VRAM GiB | Process-tree RSS GiB | Process swap GiB |
| --- | ---: | ---: | ---: | ---: |
| Fresh process | 365.76 | 15.77 | 21.97 | 3.71 |
| Warm session, excluded warmup | 362.13 | 15.78 | 23.09 | 3.16 |
| Warm repeat 1 | 82.23 | 15.18 | 21.30 | 3.54 |
| Warm repeat 2 | 78.17 | 15.62 | 20.95 | 3.58 |

The two measured warm runs have a median of 80.20 seconds, with later client-observed sampler-step intervals averaging about 8.19 seconds. This measures cache reuse within this session, not a matched ROCm 7.2-to-10 performance improvement. Two repeats do not establish a broad speed guarantee, and swap and VAE fallback remain present. See the [warm report](/home/litan/Projects/bfaceswap/benchmarks/optimization/rocm10-legacy-warm/report.json).

The reference panel is absent in inspected frames 0, 16 and 32 and an ordered 33-frame face sheet, but framing recenters and the source's open mouth remains reduced, similar to the historical sample. Eyes retain a stylized appearance. Isolated headless Chrome playback completed for the dynamic artifact, fresh output and final warm output, with 33 presented frames and zero dropped or corrupted frames in each check; see [fresh playback](/home/litan/Projects/bfaceswap/logs/playback-rocm10-legacy-fresh-baseline-1.json), [warm playback](/home/litan/Projects/bfaceswap/logs/playback-rocm10-legacy-warm-baseline-3.json) and [dynamic playback](/home/litan/Projects/bfaceswap/logs/playback-rocm10-dynamic-artifact.json). This technical playback check and ordered frames do not establish accepted temporal likeness or mouth-motion quality on user inputs. Quality remains unaccepted.

During the initial migration the BFS unit suite passed all 57 tests after the launcher/installer changes, and the documented `install-bfs.sh --check` passed with the custom SDK environment. Those verification servers were stopped only after terminal jobs and empty queues were recorded. That initial stage preserved `/opt/comfyui`, the old llama.cpp build, ComfyUI/node and llama.cpp source revisions, package inventory and Git indexes; the later legacy removal intentionally changed the package inventory as recorded above. No commit or staging operation was performed.

## llama.cpp status

At source `5676dfbe01e7ebe0387913680eee0ed39bf4a363`, the fresh Release build completed for `llama-bench` and `llama-completion`. The earlier `build/` was retained. Use the SDK environment above and run:

```bash
cd /home/litan/Projects/llama_cpp
HIPCXX="$ROCM_PATH/lib/llvm/bin/clang" cmake -S . -B build-rocm10 \
  -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON -DGPU_TARGETS=gfx1200 \
  -DCMAKE_PREFIX_PATH="$ROCM_PATH" -DCMAKE_HIP_COMPILER_ROCM_ROOT="$ROCM_PATH" \
  -DCMAKE_BUILD_RPATH="$ROCM_PATH/lib;$ROCM_PATH/lib/llvm/lib"
cmake --build build-rocm10 --target llama-bench llama-completion --parallel 4
env -u LD_LIBRARY_PATH ldd build-rocm10/bin/libggml-hip.so
```

Embedding the build runtime paths matters: before that correction, bare execution could resolve the older system libraries. The [final linkage checks](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/llama-linkage-rpath-after.log) and independent root check found no unresolved dependencies or `/opt/rocm` resolutions with `LD_LIBRARY_PATH` unset. No CMake policy compatibility flag or source changes were required. This builds the two verified tools; it does not rebuild the existing server or install them globally.

GPU inference with the cached Ornith 9B Q8_0 model returned `Paris` for `The capital of France is` at seed 42 and temperature 0. The [fixed workload record](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/llama-workload.json) contains its 9,527,500,992-byte size and verified SHA-256. Exact inference/benchmark commands, timings and exit codes are in [llama-execution-after.json](/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/llama-execution-after.json).

The fixed `llama-bench -p 128 -n 32 -r 3 -ngl 999 -o json` workload ran in fresh processes, with its default warmup and three internal repetitions. The older binary observed 1,450.45 prompt tokens/s and 31.12 generation tokens/s; the new build observed 1,612.09 and 31.64 respectively. OS/model cache was uncontrolled and an unrelated host encoding workload remained active. The old build commit `f449e0553` differs from `5676dfbe0`, so these observations cannot isolate ROCm or establish a repeatable speedup.

---

## Workload optimization execution (2026-11-14)

The [workload execution record](rocm10-workload-optimization.md) contains the
frozen environment, raw benchmark references, code verification, and pending
gates. The native `llama-server` and pinned whisper.cpp v1.9.5 HIP executable now
build and resolve the selected SDK libraries. Whisper and Qwen model downloads
were deferred, so real subtitle inference is not validated by those builds.

BFS produced two valid fresh measurements, then encountered an SDMA0 GPU fault;
two other attempts exited 143 for an unknown reason. A post-fault finite-kernel
check passed, but repeated render stability is unresolved. Matched attention
profiles are available for opt-in experiments; the production `legacy` default
is unchanged. Do not treat the historical results above as evidence for these
new candidates.

## Historical: CTranslate2 with ROCm 7.2 on CachyOS

Date: June 2026. The following is historical, not a ROCm 10 verification.

This covers installing ROCm 7.2 from the Arch `extra` repository and building CTranslate2 with the HIP backend. Tested on CachyOS (kernel `7.0.12-1-cachyos`) with an RX 9060 XT (gfx1200 / RDNA4) discrete GPU alongside a Ryzen 9600X integrated GPU. CachyOS is Arch-based so all `pacman` commands apply as-is.

---

### Prerequisites

- Arch Linux with an up-to-date system
- A supported AMD GPU (RDNA4 / gfx1200, e.g. RX 9060 XT)
- `base-devel`, `cmake`, and `git` installed

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel cmake git
```

---

### 1. Install the ROCm HIP SDK

At the time of this record, ROCm 7.2 was in the official `extra` repo (version 7.2.4-1).

```bash
sudo pacman -S rocm-hip-sdk
```

This pulls in `rocm-llvm`, `rocblas`, `hipblas`, `hipblaslt`, `hiprand`, `hipcub`, `rocprim`, `rocthrust`, `miopen-hip`, and the HIP runtime as dependencies — all required for the CTranslate2 HIP build. Verify the install:

```bash
pacman -Qi rocm-hip-sdk | grep Version
/opt/rocm/bin/hipconfig --version
```

`hipconfig` is not in PATH until step 3; use the full path here.

---

### 2. Add your user to the GPU groups

```bash
sudo usermod -aG render,video $USER
```

Log out and back in (or `newgrp render`) for the group change to take effect.

---

### 3. Set up environment variables

Add to `~/.bashrc`:

```bash
export ROCM_PATH=/opt/rocm
export PATH="$ROCM_PATH/bin:$PATH"
```

Reload the shell or open a new terminal to pick up the changes.

`HSA_OVERRIDE_GFX_VERSION` is not needed on this hardware — ROCm 7.2 correctly identifies the RX 9060 XT as `gfx1200` without it.

---

### 4. Verify ROCm sees the GPU

```bash
rocminfo | grep -E 'Name|gfx'
```

Expected output (abridged):

```
Name:                    gfx1200
Marketing Name:          AMD Radeon RX 9060 XT
Name:                    gfx1036
Marketing Name:          AMD Ryzen 5 9600X 6-Core Processor
```

The discrete RX 9060 XT is `gfx1200`; the Ryzen 9600X iGPU is `gfx1036`. Verify device identity and index with the available ROCm tools before selecting a device.

---

### 5. Clone CTranslate2

```bash
git clone --recursive https://github.com/OpenNMT/CTranslate2.git
cd CTranslate2
```

---

### 6. Build CTranslate2 with HIP

CTranslate2 requires a CPU math backend in addition to the GPU backend. On Arch the simplest option without Intel dependencies is **OpenBLAS** combined with the compiler's OpenMP runtime. Alternatively, use `WITH_MKL=ON` if Intel oneAPI MKL is installed.

#### Option A — OpenBLAS (recommended for Arch / no Intel tools)

Install OpenBLAS **before** running cmake (CachyOS users: the optimised build is in `cachyos-znver4/openblas`):

```bash
sudo pacman -S openblas
```

Then configure and build (run from the repo root):

```bash
cmake -S . -B build \
  -DCMAKE_C_COMPILER=/opt/rocm/bin/amdclang \
  -DCMAKE_CXX_COMPILER=/opt/rocm/bin/amdclang++ \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/opt/rocm \
  -DCMAKE_HIP_ARCHITECTURES="gfx1200" \
  -DWITH_HIP=ON \
  -DWITH_MKL=OFF \
  -DWITH_OPENBLAS=ON \
  -DOPENMP_RUNTIME=COMP \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_CXX_FLAGS="-Wno-deprecated-literal-operator" \
  -DCMAKE_HIP_FLAGS="-Wno-deprecated-literal-operator"

cmake --build build -- -j$(nproc)
```

#### Option B — Intel MKL (if oneAPI is installed)

```bash
sudo pacman -S intel-oneapi-mkl   # AUR or manual install
```

```bash
cmake -S . -B build \
  -DCMAKE_C_COMPILER=/opt/rocm/bin/amdclang \
  -DCMAKE_CXX_COMPILER=/opt/rocm/bin/amdclang++ \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/opt/rocm \
  -DCMAKE_HIP_ARCHITECTURES="gfx1200" \
  -DWITH_HIP=ON \
  -DWITH_MKL=ON \
  -DOPENMP_RUNTIME=COMP \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DCMAKE_CXX_FLAGS="-msse4.1 -Wno-deprecated-literal-operator" \
  -DCMAKE_HIP_FLAGS="-Wno-deprecated-literal-operator"

cmake --build build -- -j$(nproc)
```

**Dual-GPU note:** Both the RX 9060 XT (gfx1200) and the Ryzen 9600X iGPU (gfx1036) will be visible to ROCm. Passing `gfx1200` to `CMAKE_HIP_ARCHITECTURES` compiles kernels only for the discrete card, which is what you want.

Binaries land in `build/` and the shared library in `build/libctranslate2.so`.

---

### 7. (Optional) Install system-wide

```bash
sudo cmake --install build
sudo ldconfig
```

Default prefix is `/usr/local`. Override with `-DCMAKE_INSTALL_PREFIX=<path>` during configure.

---

### 8. (Optional) Build the Python wheel

After step 6/7:

```bash
cd python
pip install -r install_requirements.txt
CTRANSLATE2_ROOT=/usr/local python setup.py bdist_wheel
pip install dist/*.whl
```

If CTranslate2 was installed to a custom prefix, set both `CTRANSLATE2_ROOT` and `LD_LIBRARY_PATH` accordingly.

---

### 9. Runtime notes

- **Select discrete GPU:** `HIP_VISIBLE_DEVICES=0` (discrete is usually index 0; verify with `rocm-smi`)
- **Check device:** `CTRANSLATE2_VERBOSE=1` will print the device selected at runtime

Example usage with the discrete GPU:

```bash
HIP_VISIBLE_DEVICES=0 ct2-translator --model /path/to/model --device cuda ...
```

(`--device cuda` is the correct flag even on ROCm — CTranslate2 uses the CUDA device type name for HIP.)

---

### 10. Verify the build

**Check the shared library exists:**

```bash
ls -lh build/libctranslate2.so*
```

Library versions and sizes depend on the build.

**Confirm all HIP/ROCm deps resolve (no missing libraries):**

```bash
ldd build/libctranslate2.so | grep 'not found'
```

No output means no unresolved dependencies were reported. Inspect the full `ldd` output to verify where each ROCm library resolved. If anything is missing, check the selected SDK installation and library paths.

**Confirm HIP kernels are compiled in:**

```bash
nm -D build/libctranslate2.so | grep -c hip
```

A symbol count is only a build diagnostic. It does not establish GPU kernel execution; require a device probe and real inference on the intended GPU.

**List detected GPU devices (Python, from build directory):**

```bash
HIP_VISIBLE_DEVICES=0 LD_LIBRARY_PATH=build:$LD_LIBRARY_PATH \
  .venv/bin/python -c "
import ctranslate2
print('version:', ctranslate2.__version__)
print('HIP devices:', ctranslate2.get_cuda_device_count())
"
```

> **Note:** The Python venv's editable install must point to the current project path. If you get `No module named 'ctranslate2'`, the venv was built against an old path — rebuild the wheel (§8) or reinstall with `pip install -e python/`.

**Monitor GPU load** (separate terminal):

```bash
watch -n 1 rocm-smi
```

GPU utilization should spike during translation inference.

---

### Troubleshooting

| Symptom | Fix |
|---|---|
| `CMake Error … Compatibility with CMake < 3.5 has been removed` | Add `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` to the cmake command (CMake 4.x + old `cpu_features` submodule) |
| `hipconfig: command not found` | Ensure `$ROCM_PATH/bin` is in `PATH`; reinstall `rocm-hip-sdk` |
| `amdclang++: command not found` | Use full path `/opt/rocm/bin/amdclang++` or add `/opt/rocm/bin` to PATH |
| `Could not find hiprand / hipblas / rocprim …` | Pass `-DCMAKE_PREFIX_PATH=/opt/rocm` to cmake; ensure `rocm-hip-sdk` 7.2+ is installed |
| `error: HSA_STATUS_ERROR_INVALID_ISA` | Check the selected device architecture and the architectures compiled into the build; investigate before applying an ISA override |
| `hipblaslt` link errors | Confirm `rocm-hip-sdk` 7.2+ is installed; it includes `hipblaslt` |
| Permission denied on `/dev/kfd` or `/dev/dri` | Confirm `render` and `video` group membership, then re-login |
| ROCm sees wrong GPU count | Use `HIP_VISIBLE_DEVICES` to select the correct device index |
| Linker errors with OpenBLAS | Confirm `openblas` package is installed and `OPENBLAS_INCLUDE_DIR` is found |
