#!/usr/bin/env python3
import os
import argparse
from pathlib import Path
import subprocess
import tempfile
import sys
import srt


# --- GPU Override for AMD RX 9060 XT ---
# Kept in case the underlying libraries used by llama-cli need it.
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "12.0.0"
os.environ["HIP_VISIBLE_DEVICES"] = "0"


def main():
    """
    Main function to handle command-line arguments and orchestrate the SRT translation process.
    """
    parser = argparse.ArgumentParser(
        description="Translates SRT files by chunking them to fit into a model's context window.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # --- Input/Output Arguments ---
    parser.add_argument("-i", "--input_path", required=True, help="Path to a single .srt file or a directory containing .srt files.")
    parser.add_argument("-o", "--output_directory", help="Directory to save translated files. Defaults to the input file's directory.")
    parser.add_argument("-sl", "--source_lang", default="Japanese", help="Source language for the translation prompt (e.g., 'Japanese').")
    parser.add_argument("-tl", "--target_lang", default="Simplified Chinese", help="Target language for the translation prompt (e.g., 'Simplified Chinese').")
    
    # --- LLaMA.cpp Model and Execution Arguments ---
    parser.add_argument("-m", "--model", dest="model_path", default=os.path.expanduser("/home/li-tan/.cache/llama.cpp/Qwen_Qwen2.5-14B-Instruct-GGUF_qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"), help="Path to the LLaMA GGUF model file.")
    parser.add_argument("-c", "--llama_cli_path", default=os.path.expanduser("~/llama_cpp/build/bin/llama-cli"), help="Path to the llama-cli executable.")

    # --- Chunking Argument ---
    parser.add_argument("--chunk-size", type=int, default=50, help="Number of subtitle entries to process in a single chunk.")

    args = parser.parse_args()

    # --- Discover SRT Files ---
    input_path = Path(args.input_path)
    files_to_process = []
    if input_path.is_dir():
        print(f"Searching for .srt files in directory: {input_path}")
        files_to_process.extend(sorted(input_path.rglob("*.srt")))
    elif input_path.is_file() and input_path.suffix.lower() == ".srt":
        files_to_process.append(input_path)

    if not files_to_process:
        print("No .srt files found to process.")
        return

    print(f"Found {len(files_to_process)} file(s) to translate.")
    print("---")

    # --- Process Each File ---
    for srt_file in files_to_process:
        print(f"Processing: {srt_file.name}")
        try:
            # --- Determine Output Path ---
            if args.output_directory:
                output_dir = Path(args.output_directory)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{srt_file.stem}.zh.srt"
            else:
                output_path = srt_file.with_name(f"{srt_file.stem}.zh.srt")
            
            if output_path.exists():
                print(f"Skipping, output file already exists: {output_path}")
                print("---")
                continue

            # --- Read and Parse SRT File ---
            srt_content = srt_file.read_text(encoding="utf-8")
            try:
                subtitles = list(srt.parse(srt_content))
            except Exception as e:
                print(f"Error parsing SRT file {srt_file.name}, it may be malformed. Error: {e}", file=sys.stderr)
                continue

            # --- Chunk Subtitles ---
            subtitle_chunks = [subtitles[i:i + args.chunk_size] for i in range(0, len(subtitles), args.chunk_size)]
            translated_subtitles = []
            print(f"Split {srt_file.name} into {len(subtitle_chunks)} chunks of up to {args.chunk_size} subtitles each.")

            # --- Translate Each Chunk ---
            for i, chunk in enumerate(subtitle_chunks):
                print(f"  - Translating chunk {i+1}/{len(subtitle_chunks)}...")
                chunk_srt_content = srt.compose(chunk)

                prompt = (
                    f"You are a professional translator. Translate the following {args.source_lang} "
                    f"SRT content to {args.target_lang}. Keep timestamps and formatting intact. "
                    f"Do not add any extra commentary or notes outside of the translation itself:\n\n"
                    f"{chunk_srt_content}"
                )

                command = [
                    args.llama_cli_path,
                    "-m", args.model_path,
                    "-ngl", "35",              # Use 35 out of 40 GPU layers
                    "-fa", "on",                # Flash Attention (Crucial for VRAM)
                    "-c", "16384",              # Reduced from 32k to 16k (Safe for 14B models on 16GB VRAM)
                    "-ctk", "q8_0",             # NEW: Quantize Key cache (Saves 50% VRAM)
                    "-ctv", "q8_0",             # NEW: Quantize Value cache (Saves 50% VRAM)
                    "-n", "-1",                 # Ensure full translation (now default, but good for safety)
                    # "--log-disable",            # Keep it silent
                    "--no-display-prompt",      # Don't echo the SRT back to terminal
                    # "--no-perf",                # Clean output
                    "--simple-io"               # Helps Python read the output stream
                ]

                # Pass the prompt via stdin to avoid interactive mode
                result = subprocess.run(
                    command,
                    input=prompt,
                    check=True,
                    text=True,
                    encoding='utf-8',
                    capture_output=True
                )

                # If subprocess failed before result is set
                if result is None:
                    raise Exception("llama-cli execution failed without a result object.")

                translated_chunk_str = result.stdout.strip()

                # The model might sometimes add commentary before the SRT block, find the start
                first_line_index = translated_chunk_str.find("1\n00:")
                if first_line_index > 0:
                    print("    (Model added preliminary text, attempting to trim...)")
                    translated_chunk_str = translated_chunk_str[first_line_index:]

                try:
                    translated_chunk = list(srt.parse(translated_chunk_str))
                    if not translated_chunk:
                        raise srt.SRTParseError("Parsed an empty list of subtitles.")
                    translated_subtitles.extend(translated_chunk)
                except Exception:
                    print(f"    WARNING: Failed to parse translated chunk {i+1}. The model may have returned an invalid SRT format. See raw output below.", file=sys.stderr)
                    print("    " + "-"*20 + " RAW CHUNK OUTPUT " + "-"*20, file=sys.stderr)
                    print(translated_chunk_str, file=sys.stderr)
                    print("    " + "-"*58, file=sys.stderr)


            # --- Reassemble and Write Final SRT ---
            if not translated_subtitles:
                print(f"Translation failed for all chunks of {srt_file.name}.", file=sys.stderr)
                continue
            
            # Re-index all subtitles sequentially before composing the final file
            for idx, sub in enumerate(translated_subtitles, 1):
                sub.index = idx
                
            final_srt_content = srt.compose(translated_subtitles)
            output_path.write_text(final_srt_content, encoding="utf-8")
            print(f"Successfully saved translated file to: {output_path}")

        except FileNotFoundError:
            print(f"Error: llama-cli not found at '{args.llama_cli_path}'. Please specify the correct path using --llama_cli_path.", file=sys.stderr)
            return
        except subprocess.CalledProcessError as e:
            print(f"Error processing chunk for {srt_file.name}. llama-cli exited with code {e.returncode}.", file=sys.stderr)
            # Print stdout and stderr from the failed process for debugging
            if e.stdout:
                print(f"--- llama-cli stdout on error ---\n{e.stdout}", file=sys.stderr)
            if e.stderr:
                print(f"--- llama-cli stderr on error ---\n{e.stderr}", file=sys.stderr)
        except Exception as e:
            print(f"An unexpected error occurred while processing {srt_file.name}: {e}", file=sys.stderr)
        finally:
            print("---")

    print("Script finished.")

if __name__ == "__main__":
    main()
