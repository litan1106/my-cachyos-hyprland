#!/usr/bin/env python3
"""
Stage 2: Transcribe audio/video files to SRT using whisper.cpp with AMD ROCm HIP.

whisper.cpp is called as a subprocess (same pattern as translate_srt.py → llama-cli).
It supports native HIP (AMD ROCm) via -DGGML_HIP=ON at build time, unlike
faster-whisper/CTranslate2 which requires a real NVIDIA CUDA driver.

See AGENTS.md for build instructions.
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path

# --- ROCm Environment ---
# Must be set before any subprocess that touches GPU libraries.
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "12.0.0"   # Treat gfx1200 as supported gfx12
os.environ["HIP_VISIBLE_DEVICES"] = "0"              # Discrete RX 9060 XT only
os.environ["ROCR_VISIBLE_DEVICES"] = "0"             # ROCm runtime device selection

# Ensure ROCm HIP libraries are on LD_LIBRARY_PATH for the whisper-cli subprocess.
_rocm_lib = "/opt/rocm/lib"
_ld = os.environ.get("LD_LIBRARY_PATH", "")
if _rocm_lib not in _ld:
    os.environ["LD_LIBRARY_PATH"] = _rocm_lib + (":" + _ld if _ld else "")

COMPATIBLE_EXTENSIONS = [".wav", ".mp4", ".mkv", ".mp3", ".m4a", ".mov"]

DEFAULT_MODEL = os.path.expanduser("~/whisper_cpp/models/ggml-large-v3-q5_0.bin")
DEFAULT_CLI   = os.path.expanduser("~/whisper_cpp/build/bin/whisper-cli")


def main():
    parser = argparse.ArgumentParser(
        description="Transcribes audio/video files to SRT using whisper.cpp (AMD ROCm HIP).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-i", "--input_path", required=True,
                        help="Single file or directory to transcribe.")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help="Path to the GGML model file (default: ggml-large-v3-q5_0.bin).")
    parser.add_argument("-l", "--language", default="ja",
                        help="BCP-47 language code of source audio (default: ja).")
    parser.add_argument("-o", "--output_directory",
                        help="Directory to save .srt files. Defaults to same dir as input.")
    parser.add_argument("-w", "--whisper_cli", default=DEFAULT_CLI,
                        help="Path to the whisper-cli binary.")
    parser.add_argument("-t", "--threads", type=int, default=4,
                        help="CPU threads for pre/post-processing (default: 4).")
    args = parser.parse_args()

    # --- Discover files ---
    input_path = Path(args.input_path)
    files_to_process = []
    if input_path.is_dir():
        print(f"Searching for files in directory: {input_path}")
        for ext in COMPATIBLE_EXTENSIONS:
            files_to_process.extend(sorted(input_path.rglob(f"*{ext}")))
    elif input_path.is_file() and input_path.suffix.lower() in COMPATIBLE_EXTENSIONS:
        files_to_process.append(input_path)

    if not files_to_process:
        print("No compatible audio/video files found.")
        return

    print(f"Found {len(files_to_process)} file(s) to transcribe.")
    print("---")

    whisper_cli = os.path.expanduser(args.whisper_cli)
    model_path  = os.path.expanduser(args.model)

    for audio_file in files_to_process:
        print(f"Processing: {audio_file.name}")
        try:
            # --- Determine output path ---
            if args.output_directory:
                output_dir = Path(args.output_directory)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_stem = output_dir / audio_file.stem
            else:
                output_stem = audio_file.parent / audio_file.stem

            output_srt = output_stem.with_suffix(".srt")

            if output_srt.exists():
                print(f"Skipping, output already exists: {output_srt}")
                print("---")
                continue

            # --- Run whisper-cli ---
            # -osrt : write SRT file
            # -of   : output file prefix (whisper-cli appends .srt automatically)
            command = [
                whisper_cli,
                "-m", model_path,
                "-f", str(audio_file),
                "-l", args.language,
                "-t", str(args.threads),
                "-osrt",
                "-of", str(output_stem),
            ]

            print(f"Transcribing → {output_srt}")
            subprocess.run(command, check=True, env=os.environ)
            print(f"Saved: {output_srt}")

        except FileNotFoundError:
            print(
                f"Error: whisper-cli not found at '{whisper_cli}'.\n"
                "Build whisper.cpp with HIP support — see AGENTS.md for build instructions.",
                file=sys.stderr,
            )
            return
        except subprocess.CalledProcessError as e:
            print(f"Error: whisper-cli exited with code {e.returncode} for {audio_file.name}.",
                  file=sys.stderr)
        finally:
            print("---")

    print("Script finished.")


if __name__ == "__main__":
    main()