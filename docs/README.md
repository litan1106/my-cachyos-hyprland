# Documentation

Start with the [repository README](../README.md) for installation, active
shortcuts, machine-specific display/input settings, and updates. Repository
script examples run from the repository root unless a guide changes directory.

## Desktop customization

| Guide | Purpose |
| --- | --- |
| [Noctalia layout](../noctalia-v5/README.md) | Optional bar and Dock layout, local preferences, and overlay behavior. |
| [Omarchy theme picker](../noctalia-v5/omarchy-themes/README.md) | Palette selection, terminal commands, pinned sources, and regeneration. |
| [Omarchy keymap reference](omarchy-keymap.md) | Upstream shortcut reference; use the repository README for this setup's active shortcuts. |

## Scripts and backups

| Guide | Purpose |
| --- | --- |
| [Scripts guide](scripts-guide.md) | Backup, gaming, Waydroid, network, and development-tool utilities. |
| [VS Code configuration transfer](scripts-guide.md#backup-vscodesh) | Linux-to-Linux profile snapshots, extensions, exclusions, and recovery. |
| [Antigravity customization walkthrough](agy-artifact-custom-command-walkthrough.md) | Machine-local artifact-manager and status-line configuration record; the implementations are outside this repository. |

## Editors

| Guide | Purpose |
| --- | --- |
| [VS Code to Zed](vscode-to-zed-guide.md) | Settings, keybindings, extensions, and editor concepts. |

## GPU and AI workflows

These guides record different environments. Check the version and hardware scope
before using commands. Absolute evidence paths refer to artifacts on the original
machine, outside this repository.

| Guide | Purpose |
| --- | --- |
| [ROCm on CachyOS](rocm-install-arch.md) | Recorded ROCm 10 SDK, llama.cpp tools, and BFS migration, with measured limits and a historical ROCm 7.2 CTranslate2 appendix. |
| [llama.cpp with ROCm 7.2](llama_rocm-install-arch.md) | Historical build and runtime procedure, linked to the shared ROCm 7.2 prerequisites. |
| [Qwythos with llama-server](llama_qwythos.md) | Recorded ROCm 7.2 model and VS Code configuration; unfinished benchmarks are identified in the guide. |
| [ComfyUI installation notes](comfyui-install.md) | Copied upstream notes and the distinction between the legacy system installation and the recorded BFS environment. |
| [Legacy ComfyUI ROCm helper](fix-comfyui-rocm.sh) | ROCm 7.2 repair script targeting `/opt/comfyui` and `/opt/rocm`; separate from the ROCm 10 BFS workflow. |

## Historical plans

| Record | Purpose |
| --- | --- |
| [2026-11-12 ROCm upgrade plan](superpowers/plans/2026-11-12-rocm-10-upgrade.md) | Original proposal and execution amendments. Use the ROCm guide for the recorded installed state; the plan retains superseded steps. |
