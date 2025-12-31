import os
import re
import shutil
import subprocess
import argparse
import math
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

# Comma-separated folders to scan
folders = r"/data"
folder_list = [f.strip() for f in folders.split(",") if f.strip()]

# REGEX PATTERNS

# ISO pattern 1: username=_=timestamp
pattern_iso_eq = re.compile(
    r'^(.*)=_=(\d{4}-\d{2}-\d{2}T\d{6}(?:\.\d{3})?Z)(?:[_A-Za-z0-9\+\-]+)?(?:\s*\(\d+\))?\.(.+)$'
)

# ISO pattern 2: username__timestamp
pattern_iso_us = re.compile(
    r'^(.*)__(\d{4}-\d{2}-\d{2}T\d{6}(?:\.\d{3})?Z)(?:[_A-Za-z0-9\+\-]+)?(?:\s*\(\d+\))?\.(.+)$'
)

# ALT pattern
pattern_alt = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}).*'
)

# Fallback pattern 1: YYMMDD<space>anything
pattern_fb_space = re.compile(
    r'^(\d{2})(\d{2})(\d{2})\s+.*'
)

# Fallback pattern 2: YYMMDD-anything
pattern_fb_dash = re.compile(
    r'^(\d{2})(\d{2})(\d{2})-.*'
)

# LOG FILES

cwd = os.getcwd()
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


# ARGUMENT PARSER

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

    return parser.parse_args()

# PROGRESS BAR

def print_progress(current, total, bar_length=40):
    if total == 0:
        return
    percent = current / total
    filled = int(bar_length * percent)
    bar = "█" * filled + "░" * (bar_length - filled)
    print(f"\rProcessing files: |{bar}| {current}/{total} ({percent*100:.1f}%)", end="", flush=True)


# MOVE HELPERS (cross-drive safe)

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


# PROCESS FILE

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

    # ISO PATTERN 1 (=_=)
    m_iso1 = pattern_iso_eq.match(fname)
    if m_iso1:
        timestamp_str = m_iso1.group(2)
        try:
            dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%S.%fZ")
        except ValueError:
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%SZ")
            except ValueError:
                moved = move_to_failed(fpath)
                return (fname, f"ISO1 timestamp parse error → moved to {moved}", "notmatch", (size_before, size_before))

    else:
        # ISO PATTERN 2 (__)
        m_iso2 = pattern_iso_us.match(fname)
        if m_iso2:
            timestamp_str = m_iso2.group(2)
            try:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%S.%fZ")
            except ValueError:
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%SZ")
                except ValueError:
                    moved = move_to_failed(fpath)
                    return (fname, f"ISO2 timestamp parse error → moved to {moved}", "notmatch", (size_before, size_before))

        else:
            # ALT PATTERN
            m_alt = pattern_alt.match(fname)
            if m_alt:
                timestamp_str = m_alt.group(1)
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H.%M.%S")
                except ValueError:
                    moved = move_to_failed(fpath)
                    return (fname, f"ALT timestamp parse error → moved to {moved}", "notmatch", (size_before, size_before))

            else:
                # FALLBACK PATTERN 1 (YYMMDD<space>)
                m_fb1 = pattern_fb_space.match(fname)
                if m_fb1:
                    yy, mm, dd = m_fb1.groups()
                    year = int("20" + yy)
                    month = int(mm)
                    day = int(dd)
                    try:
                        dt = datetime(year, month, day, 0, 0, 0)
                        timestamp_str = f"{year}-{mm}-{dd}"
                    except ValueError:
                        moved = move_to_failed(fpath)
                        return (fname, f"Fallback1 YYMMDD parse error → moved to {moved}", "notmatch", (size_before, size_before))

                else:
                    # FALLBACK PATTERN 2 (YYMMDD-)
                    m_fb2 = pattern_fb_dash.match(fname)
                    if m_fb2:
                        yy, mm, dd = m_fb2.groups()
                        year = int("20" + yy)
                        month = int(mm)
                        day = int(dd)
                        try:
                            dt = datetime(year, month, day, 0, 0, 0)
                            timestamp_str = f"{year}-{mm}-{dd}"
                        except ValueError:
                            moved = move_to_failed(fpath)
                            return (fname, f"Fallback2 YYMMDD parse error → moved to {moved}", "notmatch", (size_before, size_before))

                    else:
                        moved = move_to_failed(fpath)
                        return (fname, f"No pattern matched → moved to {moved}", "notmatch", (size_before, size_before))

    # WRITE EXIF TIMESTAMP
    exif_timestamp = dt.strftime("%Y:%m:%d %H:%M:%S")

    # result = subprocess.run([
        # os.path.join(cwd, "exiftool"),
        # "-overwrite_original",
        # f"-DateTimeOriginal={exif_timestamp}",
        # fpath
    # ], capture_output=True, text=True)
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

    # SUCCESS
    if result.returncode == 0:
        return (fname, timestamp_str, "match", (size_before, size_after))

    # FAILURE
    err = result.stderr.strip()

    if "Not a valid JPG (looks more like a RIFF)" in err:
        moved = move_to_riff(fpath)
        return (fname, f"RIFF detected → moved to {moved}", "notmatch", (size_before, size_after))

    moved = move_to_failed(fpath)
    return (fname, f"Exiftool error: {err} → moved to {moved}", "notmatch", (size_before, size_after))


# MAIN FUNCTION

def main():
    args = parse_args()
    verbose = args.verbose

    # determine worker count based on --workers
    total_threads = os.cpu_count() or 1

    if args.workers.lower() == "all":
        workers = total_threads
    else:
        try:
            pct = int(args.workers)
            pct = max(1, min(pct, 100))
            workers = max(1, math.floor(total_threads * (pct / 100)))
        except ValueError:
            # default to 80% if invalid
            workers = max(1, math.floor(total_threads * 0.8))

    if verbose:
        print(f"Using {workers} worker processes out of {total_threads} available threads.")
    else:
        print(f"Using {workers} worker processes out of {total_threads} available threads.")

    all_files = []

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
        print()  # newline after progress bar

    print("\n=== Summary ===")
    print(f"Total files scanned: {summary['total']}")
    print(f"Matched: {summary['match']}")
    print(f"Not matched: {summary['notmatch']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Size increased: {summary['increased']}")
    print(f"Size decreased: {summary['decreased']}")

if __name__ == "__main__":
    main()