## Building CTranslate2 with ROCm on Arch Linux (CachyOS)

Date: June 2026

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

ROCm 7.2 is in the official `extra` repo (current version: 7.2.4-1).

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

Both agents appear: the discrete RX 9060 XT (`gfx1200`) and the Ryzen 9600X iGPU host agent (`gfx1036`). The iGPU also exposes a `gfx1200` compute agent (RDNA4), so you may see it listed twice. Use `rocm-smi --showid` to confirm which device index maps to the discrete card.

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
- **Use iGPU only:** `HIP_VISIBLE_DEVICES=1`
- **Force GFX detection:** `HSA_OVERRIDE_GFX_VERSION=12.0.0` (not normally needed with ROCm 7.2)
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
ls -lh build/libctranslate2.so build/libctranslate2.so.4 build/libctranslate2.so.4.8.0
```

Expected output shows a 42 MB versioned `.so` with two symlinks pointing to it.

**Confirm all HIP/ROCm deps resolve (no missing libraries):**

```bash
ldd build/libctranslate2.so | grep 'not found'
```

No output means all shared libraries (`libhipblas`, `libamdhip64`, `librocblas`, etc.) are found under `/opt/rocm/lib`. If anything is missing, ensure `rocm-hip-sdk` is installed and `/opt/rocm/lib` is in `LD_LIBRARY_PATH`.

**Confirm HIP kernels are compiled in:**

```bash
nm -D build/libctranslate2.so | grep -c hip
```

Expect ~1300+ symbols. A count of `0` means the HIP backend was not linked.

**List detected GPU devices (Python, from build directory):**

```bash
HIP_VISIBLE_DEVICES=0 LD_LIBRARY_PATH=build:$LD_LIBRARY_PATH \
  .venv/bin/python -c "
import ctranslate2
print('version:', ctranslate2.__version__)
print('HIP devices:', ctranslate2.get_cuda_device_count())
for i in range(ctranslate2.get_cuda_device_count()):
    info = ctranslate2.get_device_memory_info('cuda', i)
    print(f'  Device {i}: {info.total // 1024**2} MiB total, {info.free // 1024**2} MiB free')
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
| `error: HSA_STATUS_ERROR_INVALID_ISA` | Set `HSA_OVERRIDE_GFX_VERSION=12.0.0` to match your GPU |
| `hipblaslt` link errors | Confirm `rocm-hip-sdk` 7.2+ is installed; it includes `hipblaslt` |
| Permission denied on `/dev/kfd` or `/dev/dri` | Confirm `render` and `video` group membership, then re-login |
| ROCm sees wrong GPU count | Use `HIP_VISIBLE_DEVICES` to select the correct device index |
| Linker errors with OpenBLAS | Confirm `openblas` package is installed and `OPENBLAS_INCLUDE_DIR` is found |
