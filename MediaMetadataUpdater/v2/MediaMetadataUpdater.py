import os
import re
import shutil
import subprocess
import argparse
import math
import json
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

# Default folders (can be overridden by --directory)
folders = r"/data"

cwd = os.getcwd()

# LOG FILES
match_log = os.path.join(cwd, "0Match.log")
notmatch_log = os.path.join(cwd, "0NotMatch.log")
changed_log = os.path.join(cwd, "0FileChanged.log")

summary = {
    "total": 0,
    "match": 0,
    "notmatch": 0,
    "skipped": 0,
    "increased": 0,
    "decreased": 0
}

# Load external pattern.json
def load_external_patterns():
    json_path = os.path.join(cwd, "pattern.json")
    if not os.path.isfile(json_path):
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        patterns = []
        for item in data.get("patterns", []):
            patterns.append({
                "regex": re.compile(item["regex"]),
                "group": item.get("group", 1),
                "formats": item["formats"]
            })

        return patterns

    except Exception as e:
        print(f"Error loading pattern.json: {e}")
        return None

# Built-in fallback patterns
pattern_fb_space = re.compile(r'^(\d{2})(\d{2})(\d{2})\s+.*')
pattern_fb_dash = re.compile(r'^(\d{2})(\d{2})(\d{2})-.*')

# Built-in patterns (used only if pattern.json is missing)
builtin_patterns = [
    {
        "regex": re.compile(r'^(.*)=_=(\d{4}-\d{2}-\d{2}T\d{6}(?:\.\d{3})?Z).*'),
        "group": 2,
        "formats": ["%Y-%m-%dT%H%M%S.%fZ", "%Y-%m-%dT%H%M%SZ"]
    },
    {
        "regex": re.compile(r'^(.*)__(\d{4}-\d{2}-\d{2}T\d{6}(?:\.\d{3})?Z).*'),
        "group": 2,
        "formats": ["%Y-%m-%dT%H%M%S.%fZ", "%Y-%m-%dT%H%M%SZ"]
    },
    {
        "regex": re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}).*'),
        "group": 1,
        "formats": ["%Y-%m-%d %H.%M.%S"]
    }
]

# Argument Parser
def parse_args():
    parser = argparse.ArgumentParser(description="Media Metadata Updater")

    parser.add_argument(
        "--workers",
        default="80",
        help="Percentage of CPU threads to use (e.g., 50, 80, 100) or 'all'"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed logs for each file instead of a progress bar"
    )

    parser.add_argument(
        "--directory",
        help="Comma-separated list of directories to scan (overrides default folders)"
    )

    return parser.parse_args()

# Progress Bar
def print_progress(current, total, bar_length=40):
    if total == 0:
        return
    percent = current / total
    filled = int(bar_length * percent)
    bar = "█" * filled + "░" * (bar_length - filled)
    print(f"\rProcessing files: |{bar}| {current}/{total} ({percent*100:.1f}%)", end="", flush=True)

# Move Helpers
def safe_move(src, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    target = os.path.join(dst_dir, os.path.basename(src))
    shutil.copy2(src, target)
    os.remove(src)
    return target

def move_to_riff(fpath):
    return safe_move(fpath, os.path.join(cwd, "riff"))

def move_to_failed(fpath):
    return safe_move(fpath, os.path.join(cwd, "failed"))

def move_to_manual(fpath):
    folder = os.path.dirname(fpath)
    manual_dir = os.path.join(folder, "manual")
    os.makedirs(manual_dir, exist_ok=True)

    base = os.path.basename(fpath)
    target = os.path.join(manual_dir, base)

    if os.path.exists(target):
        name, ext = os.path.splitext(base)
        counter = 1
        while True:
            new_name = f"{name} ({counter}){ext}"
            new_target = os.path.join(manual_dir, new_name)
            if not os.path.exists(new_target):
                target = new_target
                break
            counter += 1

    shutil.copy2(fpath, target)
    os.remove(fpath)
    return target

# Process File
def process_file(fpath):
    fname = os.path.basename(fpath)
    if not os.path.isfile(fpath):
        return (fname, None, "skip", None)

    try:
        size_before = os.path.getsize(fpath)
    except OSError:
        return (fname, None, "error_size_before", None)

    timestamp_str = None
    dt = None

    # Load external patterns if available
    external = load_external_patterns()
    patterns = external if external else builtin_patterns

    # Try external/builtin patterns
    for pat in patterns:
        m = pat["regex"].match(fname)
        if m:
            timestamp_str = m.group(pat["group"])
            for fmt in pat["formats"]:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    break
                except ValueError:
                    continue
            if dt:
                break

    # If still no match, try fallback patterns
    if not dt:
        m_fb1 = pattern_fb_space.match(fname)
        if m_fb1:
            yy, mm, dd = m_fb1.groups()
            try:
                dt = datetime(int("20" + yy), int(mm), int(dd))
                timestamp_str = f"20{yy}-{mm}-{dd}"
            except ValueError:
                moved = move_to_failed(fpath)
                return (fname, f"Fallback1 YYMMDD parse error → moved to {moved}", "notmatch", (size_before, size_before))

        else:
            m_fb2 = pattern_fb_dash.match(fname)
            if m_fb2:
                yy, mm, dd = m_fb2.groups()
                try:
                    dt = datetime(int("20" + yy), int(mm), int(dd))
                    timestamp_str = f"20{yy}-{mm}-{dd}"
                except ValueError:
                    moved = move_to_failed(fpath)
                    return (fname, f"Fallback2 YYMMDD parse error → moved to {moved}", "notmatch", (size_before, size_before))
            else:
                moved = move_to_failed(fpath)
                return (fname, f"No pattern matched → moved to {moved}", "notmatch", (size_before, size_before))

    # Write EXIF timestamp
    exif_timestamp = dt.strftime("%Y:%m:%d %H:%M:%S")

    result = subprocess.run([
        os.path.join(cwd, "exiftool"),
        "-overwrite_original",
        f"-DateTimeOriginal={exif_timestamp}",
        f"-AllDates={exif_timestamp}",
        f"-CreationTime={exif_timestamp}",
        f"-ModifyDate={exif_timestamp}",
        fpath
    ], capture_output=True, text=True)

    try:
        size_after = os.path.getsize(fpath)
    except OSError:
        size_after = size_before

    if result.returncode == 0:
        return (fname, timestamp_str, "match", (size_before, size_after))

    err = result.stderr.strip()

    if "Not a valid JPG (looks more like a RIFF)" in err:
        moved = move_to_riff(fpath)
        return (fname, f"RIFF detected → moved to {moved}", "notmatch", (size_before, size_after))

    moved = move_to_failed(fpath)
    return (fname, f"Exiftool error: {err} → moved to {moved}", "notmatch", (size_before, size_after))


# Main Function
def main():
    args = parse_args()
    verbose = args.verbose

    # Worker count
    total_threads = os.cpu_count() or 1

    if args.workers.lower() == "all":
        workers = total_threads
    else:
        try:
            pct = int(args.workers)
            pct = max(1, min(pct, 100))
            workers = max(1, math.floor(total_threads * (pct / 100)))
        except ValueError:
            workers = max(1, math.floor(total_threads * 0.8))

    print(f"Using {workers} worker processes out of {total_threads} available threads.")

    # Determine directories
    if args.directory:
        folder_list = [os.path.abspath(p.strip()) for p in args.directory.split(",") if p.strip()]
        if verbose:
            print(f"Using directories from --directory: {folder_list}")
    else:
        folder_list = [f.strip() for f in folders.split(",") if f.strip()]
        if verbose:
            print(f"Using default directories: {folder_list}")

    all_files = []

    # Scan directories
    for folder in folder_list:
        if os.path.isdir(folder):
            for entry in os.listdir(folder):
                fpath = os.path.join(folder, entry)
                if os.path.isdir(fpath):
                    with open(notmatch_log, "a", encoding="utf-8") as f_notmatch:
                        f_notmatch.write(f"{entry} --> skipped directory\n")
                    if verbose:
                        print(f"Skipped directory: {entry}")
                    summary["skipped"] += 1
                else:
                    all_files.append(fpath)

    summary["total"] = len(all_files)

    completed = 0
    total = len(all_files)

    with open(match_log, "w", encoding="utf-8") as f_match, \
         open(notmatch_log, "w", encoding="utf-8") as f_notmatch, \
         open(changed_log, "w", encoding="utf-8") as f_changed, \
         ProcessPoolExecutor(max_workers=workers) as executor:

        futures = {executor.submit(process_file, fpath): fpath for fpath in all_files}

        for future in as_completed(futures):
            fname, timestamp, status, sizes = future.result()
            completed += 1

            if verbose:
                print(f"\n--- Checking file: {fname} ---")
            else:
                print_progress(completed, total)

            if status == "match":
                f_match.write(f"{fname} --> {timestamp}\n")
                if verbose:
                    print(f"Matched timestamp: {timestamp}")
                summary["match"] += 1

            elif status == "notmatch":
                f_notmatch.write(f"{fname} --> {timestamp}\n")
                if verbose:
                    print(timestamp)
                summary["notmatch"] += 1

            elif status == "skip":
                if verbose:
                    print("Skipped (not a file).")
                summary["skipped"] += 1

            else:
                f_notmatch.write(f"{fname} --> Unknown error\n")
                if verbose:
                    print("Other error, logged as not match.")
                summary["notmatch"] += 1

            if sizes:
                size_before, size_after = sizes
                if size_after > size_before:
                    f_changed.write(f"{fname} --> size increased ({size_before} → {size_after} bytes)\n")
                    if verbose:
                        print(f"File size increased ({size_before} → {size_after} bytes).")
                    summary["increased"] += 1
                elif size_after < size_before:
                    f_changed.write(f"{fname} --> size decreased ({size_before} → {size_after} bytes)\n")
                    if verbose:
                        print(f"File size decreased ({size_before} → {size_after} bytes).")
                    summary["decreased"] += 1

            if verbose:
                print(f"[{completed}/{total}] Finished processing: {fname}")

    if not verbose and total > 0:
        print()

    print("\n=== Summary ===")
    print(f"Total files scanned: {summary['total']}")
    print(f"Matched: {summary['match']}")
    print(f"Not matched: {summary['notmatch']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Size increased: {summary['increased']}")
    print(f"Size decreased: {summary['decreased']}")

if __name__ == "__main__":
    main()