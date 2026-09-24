#!/usr/bin/env python3
"""
MP3 Speed Changer Tool (resumable, chunked, parallel)
--------------------------------------------------------
Speeds up all MP3 files in a given folder using ffmpeg's atempo filter,
preserving pitch. Interactive: pick a folder, then pick a speed.

- Long files are split into small chunks and processed several at a
  time in parallel. This makes the tool resumable: if it gets
  interrupted (app frozen in the background, phone restarted, etc.),
  simply re-run it and it will pick up right where it left off.
- Ends with a full report: how many files were processed, skipped,
  or failed, total size before/after, and how long it took.

Usage:
    python3 speed_up_audio.py [folder_path]

If folder_path is not provided as an argument, the tool will ask for it.
"""

import os
import subprocess
import sys
import shutil
import time
import hashlib
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

SPEED_OPTIONS = ["1.1", "1.2", "1.3", "1.5", "1.75", "2.0", "Custom"]
CHUNK_SECONDS = 300  # 5-minute chunks
MAX_WORKERS = os.cpu_count() or 4  # process this many chunks in parallel (use all cores)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def hr(char="-", width=56):
    print(char * width)


def header(title):
    print()
    hr("=")
    print(title.center(56))
    hr("=")


def display_name(filename):
    """Reorder Arabic/RTL filenames into correct visual order for terminals
    that don't handle bidi text properly (very common on Termux)."""
    if HAS_BIDI and ARABIC_RE.search(filename):
        try:
            return get_display(filename)
        except Exception:
            return filename
    return filename


def human_size(num_bytes):
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < step:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} TB"


def format_duration(seconds):
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ------------------------------------------------------------------
# Setup / input helpers
# ------------------------------------------------------------------

def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg is not installed or not found in PATH.")
        print("Install it first (e.g. 'pkg install ffmpeg' on Termux).")
        sys.exit(1)


def get_folder_path(cli_arg):
    if cli_arg and os.path.isdir(cli_arg):
        return cli_arg

    while True:
        path = input("Enter the full path to the folder containing your MP3 files: ").strip().strip('"').strip("'")
        if os.path.isdir(path):
            return path
        print(f"'{path}' is not a valid folder. Please try again.\n")


def get_mp3_files(folder_path):
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".mp3")]
    return sorted(files)


def choose_speed():
    print("\nChoose a playback speed:")
    for i, option in enumerate(SPEED_OPTIONS, start=1):
        label = f"{option}x" if option != "Custom" else "Custom (enter your own value)"
        print(f"  {i}. {label}")

    while True:
        choice = input(f"\nEnter your choice (1-{len(SPEED_OPTIONS)}): ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(SPEED_OPTIONS)):
            print("Invalid choice, please try again.")
            continue

        idx = int(choice) - 1
        if SPEED_OPTIONS[idx] == "Custom":
            while True:
                custom = input("Enter custom speed (e.g. 1.35): ").strip()
                try:
                    val = float(custom)
                    if val <= 0:
                        raise ValueError
                    return val
                except ValueError:
                    print("Please enter a valid positive number (e.g. 1.35).")
        else:
            return float(SPEED_OPTIONS[idx])


# ------------------------------------------------------------------
# ffmpeg helpers
# ------------------------------------------------------------------

def build_atempo_chain(speed):
    """ffmpeg's atempo filter only supports 0.5-2.0. Chain filters for
    speeds outside that range."""
    if 0.5 <= speed <= 2.0:
        return f"atempo={speed}"

    filters = []
    remaining = speed
    if remaining > 2.0:
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining}")
    else:
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining}")

    return ",".join(filters)


def run_ffmpeg(cmd):
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return result.returncode == 0, result.stderr.decode(errors="ignore")


def file_signature(path):
    stat = os.stat(path)
    raw = f"{os.path.basename(path)}::{stat.st_size}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def normalize_name(name):
    return unicodedata.normalize("NFC", name)


def load_completed_log(output_folder):
    """Read the list of original filenames already fully processed in a
    previous run, regardless of the exact output filename format used."""
    log_path = os.path.join(output_folder, ".completed.txt")
    done = set()
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        done.add(normalize_name(line))
        except OSError:
            pass
    return done


def append_completed_log(output_folder, filename):
    log_path = os.path.join(output_folder, ".completed.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(normalize_name(filename) + "\n")
    except OSError:
        pass


def find_existing_output(output_folder, name, ext):
    """Broad fallback match: any file in output_folder that starts with the
    original base name, regardless of the exact speed-suffix formatting.
    Catches outputs produced by older versions of this tool."""
    try:
        for f in os.listdir(output_folder):
            if f.startswith(name + "_") and f.lower().endswith(ext.lower()):
                return f
    except OSError:
        pass
    return None


def segment_input(local_input, work_dir):
    done_flag = os.path.join(work_dir, "segmented.flag")
    if os.path.exists(done_flag):
        return True

    segments_dir = os.path.join(work_dir, "segments")
    os.makedirs(segments_dir, exist_ok=True)

    pattern = os.path.join(segments_dir, "part_%04d.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", local_input,
        "-f", "segment",
        "-segment_time", str(CHUNK_SECONDS),
        "-c", "copy",
        "-reset_timestamps", "1",
        pattern,
    ]
    ok, _ = run_ffmpeg(cmd)
    if not ok:
        return False

    MIN_SEGMENT_BYTES = 2000
    for f in os.listdir(segments_dir):
        fpath = os.path.join(segments_dir, f)
        if os.path.isfile(fpath) and os.path.getsize(fpath) < MIN_SEGMENT_BYTES:
            os.remove(fpath)

    with open(done_flag, "w") as f:
        f.write("done")
    return True


def speed_up_segments(work_dir, speed):
    segments_dir = os.path.join(work_dir, "segments")
    sped_dir = os.path.join(work_dir, "sped")
    os.makedirs(sped_dir, exist_ok=True)

    segment_files = sorted(
        f for f in os.listdir(segments_dir) if f.startswith("part_") and f.endswith(".mp3")
    )
    total = len(segment_files)
    filter_chain = build_atempo_chain(speed)

    to_process = [s for s in segment_files if not os.path.exists(os.path.join(sped_dir, s))]
    already_done = total - len(to_process)

    progress_lock = threading.Lock()
    state = {"done": already_done, "failed": False}

    def process_one(seg_name):
        in_path = os.path.join(segments_dir, seg_name)
        out_path = os.path.join(sped_dir, seg_name)
        cmd = [
            "ffmpeg", "-y",
            "-i", in_path,
            "-filter:a", filter_chain,
            "-vn",
            "-b:a", "96k",
            "-compression_level", "7",  # faster MP3 encoding (0=best/slowest, 9=fastest)
            out_path,
        ]
        ok, _ = run_ffmpeg(cmd)
        with progress_lock:
            if ok:
                state["done"] += 1
            else:
                state["failed"] = True
            pct = int((state["done"] / total) * 100) if total else 100
            bar_len = 20
            filled = int(bar_len * state["done"] / total) if total else bar_len
            bar = "#" * filled + "-" * (bar_len - filled)
            print(f"\r  [{bar}] {pct:3d}%  ({state['done']}/{total} chunks)   ", end="", flush=True)
        return ok

    if to_process:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(process_one, seg) for seg in to_process]
            for future in as_completed(futures):
                future.result()
    else:
        print(f"  [{'#' * 20}] 100%  ({total}/{total} chunks) - already done   ")

    print()
    return (not state["failed"]), total, state["done"]


def concatenate_segments(work_dir, final_local_output):
    sped_dir = os.path.join(work_dir, "sped")
    segment_files = sorted(
        f for f in os.listdir(sped_dir) if f.startswith("part_") and f.endswith(".mp3")
    )
    if not segment_files:
        return False, "No processed segments found."

    list_path = os.path.join(work_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for seg in segment_files:
            abs_path = os.path.join(sped_dir, seg)
            f.write(f"file '{abs_path}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final_local_output]
    return run_ffmpeg(cmd)


def process_one_file(input_path, final_output_path, speed, base_work_dir):
    sig = file_signature(input_path)
    work_dir = os.path.join(base_work_dir, sig)
    os.makedirs(work_dir, exist_ok=True)

    local_input = os.path.join(work_dir, "input.mp3")
    if not os.path.exists(local_input):
        print("  Step 1/4: Copying to local storage...", end="", flush=True)
        try:
            shutil.copyfile(input_path, local_input)
            print(" OK")
        except OSError as e:
            return False, f"Error copying file: {e}"
    else:
        print("  Step 1/4: Using previously copied local file. OK")

    print("  Step 2/4: Splitting into chunks...", end="", flush=True)
    if not segment_input(local_input, work_dir):
        print(" FAILED")
        return False, "Segmentation failed."
    print(" OK")

    print("  Step 3/4: Processing chunks")
    ok, total, done = speed_up_segments(work_dir, speed)
    if not ok:
        return False, f"Failed while processing chunk {done + 1}/{total}. Re-run the tool to resume."

    local_final = os.path.join(work_dir, "final.mp3")
    if not os.path.exists(local_final):
        print("  Step 4/4: Joining chunks together...", end="", flush=True)
        ok, err = concatenate_segments(work_dir, local_final)
        if not ok:
            print(" FAILED")
            return False, f"Concatenation failed: {err.strip().splitlines()[-1] if err.strip() else 'unknown error'}"
        print(" OK")
    else:
        print("  Step 4/4: Already joined. OK")

    print("  Saving result to output folder...", end="", flush=True)
    try:
        shutil.copyfile(local_final, final_output_path)
        print(" OK")
    except OSError as e:
        print(" FAILED")
        return False, f"Error copying result back: {e}"

    shutil.rmtree(work_dir, ignore_errors=True)
    return True, "OK"


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def show_main_menu():
    clear_screen()
    header("MP3 SPEED CHANGER")
    print("This tool speeds up MP3 files while keeping the pitch natural.")
    print()
    print("  1. Start (choose a folder and speed up MP3 files)")
    print("  2. Exit")
    while True:
        choice = input("\nEnter your choice (1-2): ").strip()
        if choice == "1":
            return "start"
        if choice == "2":
            return "exit"
        print("Invalid choice, please try again.")


def show_post_report_menu():
    print("  1. Return to main menu")
    print("  2. Exit")
    while True:
        choice = input("\nEnter your choice (1-2): ").strip()
        if choice == "1":
            return "menu"
        if choice == "2":
            return "exit"
        print("Invalid choice, please try again.")


def run_once(cli_arg):
    """Run one full folder-selection + processing + report cycle."""
    if not HAS_BIDI:
        print("NOTE: For correct display of Arabic filenames, install python-bidi:")
        print("      pip install python-bidi")
        print("      (then run this tool again)")
        print()

    folder_path = get_folder_path(cli_arg)

    mp3_files = get_mp3_files(folder_path)
    if not mp3_files:
        print(f"\nNo MP3 files found in '{folder_path}'.")
        input("\nPress Enter to continue...")
        return

    print(f"\nFound {len(mp3_files)} MP3 file(s):")
    hr()
    for i, f in enumerate(mp3_files, start=1):
        size = human_size(os.path.getsize(os.path.join(folder_path, f)))
        print(f"  [{i}] {display_name(f)}")
        print(f"       ({size})")
    hr()

    speed = choose_speed()

    output_folder = os.path.join(folder_path, f"sped_up_{speed}x")
    os.makedirs(output_folder, exist_ok=True)

    base_work_dir = os.path.join(os.path.expanduser("~"), ".speed_up_audio_work")
    os.makedirs(base_work_dir, exist_ok=True)

    start_time = time.time()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # Report tracking
    processed_ok = []      # (filename, original_size, output_size)
    skipped_done = []      # (filename, output_size)
    failed = []            # (filename, reason)

    clear_screen()
    header("PROCESSING")
    print(f"Speed:          {speed}x")
    print(f"Total files:    {len(mp3_files)}")
    print(f"Output folder:  {output_folder}")
    print("(If interrupted, just re-run this tool - it will resume automatically.)")
    hr()

    completed_log = load_completed_log(output_folder)

    for index, filename in enumerate(mp3_files, start=1):
        input_path = os.path.join(folder_path, filename)
        name, ext = os.path.splitext(filename)
        output_filename = f"{name}_{speed}x{ext}"
        final_output_path = os.path.join(output_folder, output_filename)

        print(f"\n[{index}/{len(mp3_files)}] {display_name(filename)}")

        norm_filename = normalize_name(filename)
        already_done = False
        existing_size = None

        if norm_filename in completed_log and os.path.exists(final_output_path):
            already_done = True
            existing_size = os.path.getsize(final_output_path)
        else:
            match = find_existing_output(output_folder, name, ext)
            if match:
                already_done = True
                existing_size = os.path.getsize(os.path.join(output_folder, match))
                append_completed_log(output_folder, filename)
                completed_log.add(norm_filename)

        if already_done:
            print(f"  This file already exists in the output folder (processed before) - skipping.")
            print(f"  Waiting 5 seconds before moving to the next file...", end="", flush=True)
            for _ in range(1):
                time.sleep(1)
                print(".", end="", flush=True)
            print()
            skipped_done.append((filename, existing_size))
            continue

        ok, message = process_one_file(input_path, final_output_path, speed, base_work_dir)
        if ok:
            orig_size = os.path.getsize(input_path)
            out_size = os.path.getsize(final_output_path)
            print(f"  Done. ({human_size(orig_size)} -> {human_size(out_size)})")
            processed_ok.append((filename, orig_size, out_size))
            append_completed_log(output_folder, filename)
            completed_log.add(norm_filename)
        else:
            print(f"  FAILED: {message}")
            failed.append((filename, message))

    # ---------------- Final report ----------------
    end_time = time.time()
    finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
    elapsed = end_time - start_time

    total_orig = sum(s[1] for s in processed_ok) + sum(s[1] for s in skipped_done)
    total_out = sum(s[2] for s in processed_ok) + sum(s[1] for s in skipped_done)

    clear_screen()
    header("FINAL REPORT")
    print(f"Started:              {started_at}")
    print(f"Finished:             {finished_at}")
    print(f"Time taken:           {format_duration(elapsed)}")
    print()
    print(f"Speed applied:        {speed}x")
    print(f"Source folder:")
    print(f"  {display_name(folder_path)}")
    print(f"Output folder:")
    print(f"  {display_name(output_folder)}")
    hr()
    print(f"Total files found:      {len(mp3_files)}")
    print(f"Processed successfully: {len(processed_ok)}")
    print(f"Already done (skipped): {len(skipped_done)}")
    print(f"Failed:                 {len(failed)}")
    hr()
    print(f"Total original size:    {human_size(total_orig)}")
    print(f"Total output size:      {human_size(total_out)}")
    if total_orig > 0:
        diff = total_orig - total_out
        diff_pct = (diff / total_orig) * 100
        if diff >= 0:
            print(f"Space saved:            {human_size(diff)} ({diff_pct:.0f}%)")
        else:
            print(f"Size increased by:      {human_size(abs(diff))} ({abs(diff_pct):.0f}%)")
    hr("=")

    if skipped_done:
        print(f"\nSkipped files (already existed from a previous run) - {len(skipped_done)} file(s):")
        for fname, size in skipped_done:
            print(f"  - {display_name(fname)}  ({human_size(size)})")
        hr("=")

    if failed:
        print("\nFailed files:")
        for fname, reason in failed:
            print(f"  - {display_name(fname)}")
            print(f"    Reason: {reason}")
        hr("=")

    print()


def main():
    check_ffmpeg()

    cli_arg = sys.argv[1] if len(sys.argv) > 1 else None

    while True:
        action = show_main_menu()
        if action == "exit":
            print("\nGoodbye!")
            sys.exit(0)

        run_once(cli_arg)
        cli_arg = None  # only use the command-line folder argument on the first run

        post_action = show_post_report_menu()
        if post_action == "exit":
            print("\nGoodbye!")
            sys.exit(0)
        # otherwise loop back to the main menu


if __name__ == "__main__":
    main()