import os
import re
import shutil
import subprocess
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

pattern_alt = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}).*'
)

pattern_fallback = re.compile(
    r'^(\d{2})(\d{2})(\d{2})\s+.*'
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

# MOVE HELPERS (cross-drive safe)

def move_to_riff(fpath):
    riff_dir = os.path.join(cwd, "riff")
    os.makedirs(riff_dir, exist_ok=True)
    target = os.path.join(riff_dir, os.path.basename(fpath))
    shutil.copy2(fpath, target)
    os.remove(fpath)
    return target

def move_to_failed(fpath):
    failed_dir = os.path.join(cwd, "failed")
    os.makedirs(failed_dir, exist_ok=True)
    target = os.path.join(failed_dir, os.path.basename(fpath))
    shutil.copy2(fpath, target)
    os.remove(fpath)
    return target

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

    # Try ISO pattern 1
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
        # Try ISO pattern 2
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
            # Try alternative pattern
            m_alt = pattern_alt.match(fname)
            if m_alt:
                timestamp_str = m_alt.group(1)
                try:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H.%M.%S")
                except ValueError:
                    moved = move_to_failed(fpath)
                    return (fname, f"ALT timestamp parse error → moved to {moved}", "notmatch", (size_before, size_before))

            else:
                # Try fallback pattern
                m_fb = pattern_fallback.match(fname)
                if m_fb:
                    yy, mm, dd = m_fb.groups()
                    year = int("20" + yy)
                    month = int(mm)
                    day = int(dd)

                    try:
                        dt = datetime(year, month, day, 0, 0, 0)
                        timestamp_str = f"{year}-{mm}-{dd}"
                    except ValueError:
                        moved = move_to_failed(fpath)
                        return (fname, f"Fallback YYMMDD parse error → moved to {moved}", "notmatch", (size_before, size_before))
                else:
                    moved = move_to_failed(fpath)
                    return (fname, f"No pattern matched → moved to {moved}", "notmatch", (size_before, size_before))

    # Update metadata
    exif_timestamp = dt.strftime("%Y:%m:%d %H:%M:%S")

    result = subprocess.run([
        os.path.join(cwd, "exiftool"),
        "-overwrite_original",
        f"-DateTimeOriginal={exif_timestamp}",
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

    # ANY OTHER FAILURE
    moved = move_to_failed(fpath)
    return (fname, f"Exiftool error: {err} → moved to {moved}", "notmatch", (size_before, size_after))


# MAIN FUNCTION

def main():
    all_files = []

    for folder in folder_list:
        if os.path.isdir(folder):
            for entry in os.listdir(folder):
                fpath = os.path.join(folder, entry)
                if os.path.isdir(fpath):
                    with open(notmatch_log, "a", encoding="utf-8") as f_notmatch:
                        f_notmatch.write(f"{entry} --> skipped directory\n")
                    print(f"Skipped directory: {entry}")
                    summary["skipped"] += 1
                else:
                    all_files.append(fpath)

    summary["total"] = len(all_files)

    with open(match_log, "w", encoding="utf-8") as f_match, \
         open(notmatch_log, "w", encoding="utf-8") as f_notmatch, \
         open(changed_log, "w", encoding="utf-8") as f_changed, \
         ProcessPoolExecutor() as executor:

        futures = {executor.submit(process_file, fpath): fpath for fpath in all_files}

        for future in as_completed(futures):
            fname, timestamp, status, sizes = future.result()

            print(f"\n--- Checking file: {fname} ---")

            if status == "match":
                f_match.write(f"{fname} --> {timestamp}\n")
                print(f"Matched timestamp: {timestamp}")
                summary["match"] += 1

            elif status == "notmatch":
                f_notmatch.write(f"{fname} --> {timestamp}\n")
                print(timestamp)
                summary["notmatch"] += 1

            elif status == "skip":
                print("Skipped (not a file).")
                summary["skipped"] += 1

            else:
                f_notmatch.write(f"{fname} --> Unknown error\n")
                print("Other error, logged as not match.")
                summary["notmatch"] += 1

            if sizes:
                size_before, size_after = sizes
                if size_after > size_before:
                    f_changed.write(f"{fname} --> size increased ({size_before} → {size_after} bytes)\n")
                    print(f"File size increased ({size_before} → {size_after} bytes).")
                    summary["increased"] += 1
                elif size_after < size_before:
                    f_changed.write(f"{fname} --> size decreased ({size_before} → {size_after} bytes)\n")
                    print(f"File size decreased ({size_before} → {size_after} bytes).")
                    summary["decreased"] += 1

    print("\n=== Summary ===")
    print(f"Total files scanned: {summary['total']}")
    print(f"Matched: {summary['match']}")
    print(f"Not matched: {summary['notmatch']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Size increased: {summary['increased']}")
    print(f"Size decreased: {summary['decreased']}")

if __name__ == "__main__":
    main()