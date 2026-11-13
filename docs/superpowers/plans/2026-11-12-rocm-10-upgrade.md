# ROCm 10.0 upgrade and Arch installation guide update

Date: 2026-11-12

## Execution amendments

Current installed state after the follow-up cleanup: only the ROCm 10 SDK and its locked framework environment remain installed. The 44-package ROCm 7.2 closure and `/opt/rocm` were removed. The earlier side-by-side notes below describe the first migration stage.

During execution the user replaced the missing CTranslate2 checkout and Task 3 with `/home/litan/Projects/llama_cpp`: build the HIP benchmark and completion tools in `build-rocm10/`, verify their linkage and GPU inference, and retain the existing `build/`. The guide's current location is `/home/litan/Projects/my-cachyos-hyprland/docs/rocm-install-arch.md`.

Exact 10.0 was resolved through AMD's architecture-specific archive in the user-owned prefix `/home/litan/.local/opt/rocm-10.0.0-gfx120X-all`. The pacman-owned `/opt/rocm` 7.2.4 installation and repositories remain unchanged. This is the custom-prefix alternative in Task 1, not a distribution package upgrade. The original proposal below is retained as the planning record; its CTranslate2 commands are superseded by this amendment. Actual commands, recovery files and evidence are in `/home/litan/Projects/bfaceswap/logs/rocm-10.0-upgrade/20261113T034906Z/` and the updated guide.

Execution verified the archive, native HIP arithmetic, the isolated llama.cpp build and GPU inference, locked BFS dependencies and FP32/BF16 kernels, active nodes and matching LTX-2.3 model loading, successful short-job history, video metadata/full decoding/browser playback, and separate fresh/warm measurements. The unit suite passed 57 tests. The dynamic diagnostic completed in history but its HTTP output retrieval timed out; its matching local artifact was recovered and checked. Legacy fresh/warm runs completed end to end. Dynamic VRAM remains experimental, memory pressure persists, and a repeatable ROCm-only speedup or accepted user-clip quality has not been established. The guide and BFS runtime guidance now reflect these measured gates; historical 7.2 records were retained.

At the user's subsequent request to keep only ROCm 10, the complete 44-package legacy ROCm 7.2 dependency closure was uninstalled, including system PyTorch/ONNX Runtime integrations. The old prefix and its package-owned profile/loader settings were removed; current BFS and shell defaults select the verified ROCm 10 SDK. Removal and recovery evidence is in `/home/litan/Projects/bfaceswap/logs/rocm-7.2-removal/20261113T043533Z/`. The earlier side-by-side execution notes above describe the initial migration stage, not the current installed state.

## Objective

Upgrade the CachyOS machine from ROCm 7.2 to a consistent ROCm 10.0 stack, rebuild CTranslate2, update BFS's PyTorch environment, and revise `rocm-install-arch.md` using results from the actual migration. Measure whether the upgrade improves the workloads that currently suffer from loading, offloading and memory pressure.

This document is an implementation plan. Its commands and proposed settings are not evidence that the upgrade has been completed or that performance has improved.

## Scope and constraints

- Primary repository: `/home/litan/Projects/ctranslate2_cpp`.
- Guide to update: `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`.
- Framework integration: `/home/litan/Projects/bfaceswap`.
- Target ROCm 10.0 specifically. Do not silently substitute 10.1 because a repository has moved forward.
- Preserve existing user changes, including the staged addition of `rocm-install-arch.md`.
- Keep the current build directory and historical benchmark records. Use `build-rocm10/` for the new CTranslate2 build.
- Leave `/opt/comfyui` untouched. Validate BFS through its local ComfyUI checkout at `127.0.0.1:8189`.
- Retain BFS's Python 3.12, `uv`, project `.venv`, locked dependencies and matching LTX-2.3 model family.
- Verify device identity and kernels. Do not set `HSA_OVERRIDE_GFX_VERSION` as a generic workaround.
- Do not commit, push, restart unrelated services, or modify other projects as part of this plan.
- Installation requires administrator access. Run privileged commands locally; do not put passwords in scripts, logs or chat.

## Verified starting point

Read-only checks on 2026-11-12 established:

| Component | Observed state |
|---|---|
| Host distribution | CachyOS, Arch-based |
| Installed ROCm core and HIP runtime packages | 7.2.4 |
| SDK installation method | `pacman -S rocm-hip-sdk` |
| HIP configuration executable | `/opt/rocm/bin/hipconfig`, owned by `hip-runtime-amd` |
| CTranslate2 build configuration | HIP, `gfx1200`, OpenBLAS, compiler OpenMP runtime |
| BFS PyTorch | `2.11.0+rocm7.2` |
| BFS reported HIP | `7.2.26015` |
| BFS wheel index | `https://download.pytorch.org/whl/rocm7.2` |
| Stable Arch ROCm core | 7.2.4 |
| Arch testing ROCm core and HIP runtime | 10.1-1 |
| Arch testing SDK metapackage | 10.0-1; its name/version does not pin dependency versions |
| Administrator access in this session | `sudo -n true` requires a password |

These repository versions are time-sensitive. Refresh the evidence when executing the plan. The exact source of a consistent ROCm 10.0 installation is a discovery gate, not a resolved installation command.

The BFS checkout derives its ROCm version from `torch.version.hip` and gates automatic AMD dynamic VRAM at `(7, 14)`. Updating system packages alone does not update that PyTorch build or demonstrate that dynamic VRAM initializes successfully.

## Task 1: Resolve and record the exact upgrade transaction

**Goal:** A reproducible ROCm 10.0 installation method with known dependency changes and a recovery path.

**Files:** Inspect `/etc/pacman.conf` and its included mirror lists. Modify the prerequisites and installation sections of `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`. The exact package manifest and any system configuration changes are discovery items to name before installation.

**Steps:**

1. Inspect the staged and unstaged guide changes with `git diff --cached -- rocm-install-arch.md` and `git diff -- rocm-install-arch.md`.
2. Record `pacman -Q`, `uname -r`, `df -h / /opt`, `pacman-conf --repo-list`, `pacman -Qo /opt/rocm/bin/hipconfig`, and `/opt/rocm/bin/hipconfig --version`.
3. Record the current compiler, shared-library dependencies, GPU PCI identity, active GPU workloads and framework versions. Keep commands and records free of credentials.
4. Check whether a complete ROCm 10.0 package set is available through a consistent Arch/CachyOS repository state. Inspect the runtime, compiler and math-library dependencies, rather than relying on the SDK metapackage version.
5. Account for CachyOS repositories taking priority over Arch repositories. Do not install individual testing packages into an incompatible dependency set or enable the entire testing distribution merely to obtain one ROCm package.
6. If repositories cannot provide the target consistently, evaluate AMD's versioned archive installation. Verify its checksum, host prerequisites, compiler and library contents. Document its custom prefix and package-ownership boundaries without overwriting pacman-owned files.
7. Write the exact installation commands and package or archive versions into the guide only after resolving the method. If exact 10.0 cannot be obtained consistently, report the alternative and resolve the target version before proceeding.
8. Establish recovery for the entire affected package set or custom-prefix configuration, plus framework lockfiles. Retain the old build artifacts; do not assume downgrading one runtime package is sufficient.

**Verify:** Review the transaction or archive manifest. It must select the intended compiler and runtime, resolve dependencies, fit available disk space and preserve package ownership. The guide must identify the source, version, installation prefix and recovery procedure explicitly.

**Depends on:** None.

## Task 2: Install and verify the system ROCm stack

**Goal:** ROCm 10.0 identifies the RX 9060 XT and executes a finite arithmetic kernel.

**Files:** Modify the installation, environment, device-verification and troubleshooting sections of `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`. Modify only the system configuration identified in Task 1.

**Steps:**

1. Execute the reviewed installation transaction with local administrator authentication where required. Retain its output and actual package versions.
2. Inspect the installed directory layout. AMD's new SDK uses different prefixes and packaging conventions; do not assume those conventions match Arch's repackaging.
3. Verify compiler, header, CMake configuration and library locations before setting `ROCM_PATH`, `PATH` or loader paths. Record the actual paths in the guide.
4. Run `hipconfig --version`, `rocminfo` and the installed AMD monitoring tool. Correlate the RX 9060 XT's PCI address with the `gfx1200` compute agent before selecting `HIP_VISIBLE_DEVICES`.
5. Compile and execute a minimal HIP program that allocates memory, copies inputs, performs arithmetic and compares finite results with a CPU reference. Record the source and exact compile/run commands.
6. Correct the guide's unsupported iGPU-agent claims and generic ISA-override advice. Keep only hardware mappings and workarounds supported by this machine's results.
7. Record any required reboot or session restart and verify again afterward. Do not claim the loaded driver changed merely because packages were installed.

**Verify:** The recorded runtime and compiler match the selected target; the discrete GPU is correctly identified; the HIP arithmetic probe passes without a GFX override. Do not proceed to application troubleshooting if this gate fails.

**Depends on:** Task 1.

## Task 3: Rebuild and validate CTranslate2

**Goal:** A fresh CTranslate2 build loads the intended ROCm libraries and completes GPU inference.

**Files:** Modify the CMake, Python installation, runtime and verification sections of `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`. Create build artifacts under `/home/litan/Projects/ctranslate2_cpp/build-rocm10/`. Changes to CMake or application source are discovery items only if a reproduced compatibility failure requires them.

**Steps:**

1. Record the source revision, existing build configuration, Python interpreter and extension location before rebuilding.
2. Configure `build-rocm10/` with the compiler paths verified in Task 2, `CMAKE_HIP_ARCHITECTURES=gfx1200`, `WITH_HIP=ON`, `WITH_MKL=OFF`, `WITH_OPENBLAS=ON` and `OPENMP_RUNTIME=COMP`. Retain `CMAKE_POLICY_VERSION_MINIMUM=3.5` only where the checkout still requires it.
3. Build with `cmake --build build-rocm10 --parallel 4`. Increase concurrency only if available host memory supports it.
4. Rebuild the Python extension using the repository's existing build procedure and the new library. Verify the selected interpreter and installation path; do not assume the existing `.venv/bin/python` has the same Python version as BFS.
5. Run `ldd build-rocm10/libctranslate2.so`. Check for unresolved libraries and unintended legacy ROCm paths.
6. Run a Python import/device probe that prints `ctranslate2.__file__`, its version, `get_cuda_device_count()` and `get_supported_compute_types("cuda")` with the verified discrete GPU selected.
7. Run `python/tests/test_storage_view.py::test_storageview_cuda_to_device` through the selected CTranslate2 environment. Verify it executes rather than skips.
8. Select and record a locally available translation model and fixed input, then execute an actual GPU inference smoke test. Use the same model and input for performance comparisons.
9. Replace hardcoded shared-library version filenames and the unexported `get_device_memory_info` example in the guide. Document `cuda` as the CTranslate2 device name used for HIP.

**Verify:** The build succeeds, all required libraries resolve to the intended stack, the new Python extension is imported, the GPU transfer test passes without skipping, and real inference completes with valid output. Compilation or symbol counts alone do not establish kernel execution.

**Depends on:** Task 2.

## Task 4: Upgrade BFS's PyTorch environment

**Goal:** BFS's locked Python environment uses a compatible ROCm 10.0 framework stack and starts its local ComfyUI successfully.

**Files:** Modify `/home/litan/Projects/bfaceswap/pyproject.toml`, `/home/litan/Projects/bfaceswap/uv.lock`, and framework guidance in `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`. Update BFS runtime documentation only for procedures and gates actually verified.

**Steps:**

1. Preserve the current dependency files and record the installed torch, torchvision, torchaudio and Triton versions. Existing pre-upgrade copies are under `/home/litan/Projects/bfaceswap/logs/rocm-10.1-upgrade/`; their directory name reflects the initial investigation, not a completed upgrade or the selected target.
2. Resolve matching AMD ROCm 10.0 wheels for Python 3.12 and `gfx1200`. Inspect wheel metadata and device extras before choosing pins. Do not retain the Triton 3.6 pin without compatibility evidence.
3. Update the framework pins, explicit wheel-index mappings and lockfile together. Preserve unrelated locked dependencies where resolution permits.
4. Synchronize the existing BFS environment with `uv sync --locked`.
5. Run `uv lock --check` and `uv pip check` from `/home/litan/Projects/bfaceswap`.
6. Run `ROCM_PATH=/opt/rocm HIP_VISIBLE_DEVICES=0 .venv/bin/python scripts/check-gpu.py` if Task 2 confirms that prefix; otherwise use the verified prefix and document the exact command. Require finite FP32/BF16 results matching the CPU reference.
7. Launch the project-owned ComfyUI on `127.0.0.1:8189` using the existing runtime launcher. Confirm active workflow nodes register and inspect startup logs for actual dynamic VRAM initialization. A passed version check is insufficient.
8. Verify GGUF and LoRA loading in the selected adapted LTX-2.3 graph, then run the established short workflow. Keep the pinned upstream workflow unchanged.
9. If the runtime or graph fails, follow BFS's local ROCm-debug procedure and record the failing boundary before changing settings.

**Verify:** Dependency checks pass, the expected ROCm-backed framework is imported, FP32/BF16 probes pass on the discrete GPU, required nodes register, selected models load and a short job completes in ComfyUI history. Record dynamic VRAM as enabled only if initialization succeeds.

**Depends on:** Task 2.

## Task 5: Measure outcomes and finish the guide

**Goal:** The guide contains tested instructions and separates compatibility, performance and output-quality results.

**Files:** Modify `/home/litan/Projects/ctranslate2_cpp/rocm-install-arch.md`. Retain new BFS run artifacts in its existing `logs/`, `output/` and `benchmarks/` directories. Name the CTranslate2 measurement record when the fixed workload is selected in Task 3.

**Steps:**

1. Run the fixed CTranslate2 workload from Task 3 and the established BFS short-render benchmark. Record source revision, package versions, model/workflow identity, seed, inputs and runtime settings.
2. Separate fresh-process and warm measurements. Record cache conditions and repeats; do not present one uncontrolled run as a repeatable speed guarantee.
3. For BFS, record first-step latency, later-step latency, total runtime, sampled VRAM, process-tree RAM, swap and failures. Identify the sampling method and its limitations.
4. Validate rendered dimensions, FPS and frame count, decode all frames, and inspect playback. Preserve mouth-motion and identity quality as separate acceptance gates.
5. Update the guide's tested date and version matrix only after verification. Retain the old 7.2 results as historical observations rather than relabeling them as 10.0 results.
6. Record failed checks and remaining uncertainty. Do not claim ROCm 10.0 solved loading, offloading or mouth suppression unless the measurements establish it.
7. Review both staged and unstaged diffs in each repository. Preserve the user's existing staged guide addition and avoid staging or committing new work.

**Verify:** Every completed claim in the guide has a corresponding successful command, log or inspected artifact. Review with `git diff --check`, `git diff -- rocm-install-arch.md docs/plans/2026-11-12-rocm-10-upgrade.md` and `git diff --cached -- rocm-install-arch.md` in CTranslate2. Compare BFS dependency files with their saved pre-upgrade copies because its project root is not a Git repository.

**Depends on:** Tasks 3 and 4.

## Reference sources

- [AMD ROCm 10.0 release notes](https://rocm.docs.amd.com/en/docs-10.0.0/about/release-notes.html)
- [AMD transition guide from legacy ROCm](https://rocm.docs.amd.com/en/docs-10.0.0/about/transition-guide-TheRock.html)
- [AMD PyTorch installation guidance](https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html)
- [Arch stable ROCm core package](https://archlinux.org/packages/extra/x86_64/rocm-core/)
- [Arch testing ROCm core package](https://archlinux.org/packages/extra-testing/x86_64/rocm-core/)
- [Arch testing HIP runtime package](https://archlinux.org/packages/extra-testing/x86_64/hip-runtime-amd/)
- [Arch testing HIP SDK metapackage](https://archlinux.org/packages/extra-testing/any/rocm-hip-sdk/)

The Arch links and AMD framework installation page change over time. Pin the actual artifacts and package metadata selected in Task 1; these links alone are not a reproducible version lock.
