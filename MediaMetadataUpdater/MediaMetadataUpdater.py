import os
import re
import subprocess
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

# Comma-separated folders to scan
folders = r"F:\aaaa\,F:\bbbb\,F:\cccc\"
folder_list = [f.strip() for f in folders.split(",") if f.strip()]

pattern = re.compile(
    r'^(.*?)__(\d{4}-\d{2}-\d{2}T\d{6}\.\d{3}Z)(?:_\d+)?(?:\s*\(\d+\))?\.(.+)$'
)

cwd = os.getcwd()
match_log = os.path.join(cwd, "00Match.log")
notmatch_log = os.path.join(cwd, "00NotMatch.log")
changed_log = os.path.join(cwd, "00FileChanged.log")

summary = {
    "total": 0,
    "match": 0,
    "notmatch": 0,
    "skipped": 0,
    "increased": 0,
    "decreased": 0
}

def process_file(fpath):
    """Process a single file: check regex, update metadata if matched, check size change."""
    fname = os.path.basename(fpath)
    if not os.path.isfile(fpath):
        return (fname, None, "skip", None)

    try:
        size_before = os.path.getsize(fpath)
    except OSError:
        return (fname, None, "error_size_before", None)

    match = pattern.match(fname)
    if not match:
        return (fname, None, "notmatch", (size_before, size_before))

    timestamp_str = match.group(2)
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H%M%S.%fZ")
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

        if result.returncode == 0:
            return (fname, timestamp_str, "match", (size_before, size_after))
        else:
            return (fname, None, f"exiftool_error: {result.stderr.strip()}", (size_before, size_after))

    except ValueError:
        return (fname, None, "notmatch", (size_before, size_before))


def main():
    all_files = []
    for folder in folder_list:
        if os.path.isdir(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
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
                f_notmatch.write(f"{fname}\n")
                print("No match for timestamp pattern, logged as not match.")
                summary["notmatch"] += 1
            elif status and status.startswith("exiftool_error"):
                f_notmatch.write(f"{fname}\n")
                print(f"Exiftool error: {status}")
                summary["notmatch"] += 1
            elif status == "skip":
                print("Skipped (not a file).")
                summary["skipped"] += 1
            else:
                f_notmatch.write(f"{fname}\n")
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