import os
import sys
import subprocess
import shutil

# Global counters
total_scanned = 0
changed_to_webp = 0
not_changed = 0

def run_exiftool(filepath):
    """Run exiftool and return the value of 'File Type'."""
    try:
        result = subprocess.run(
            ["exiftool", "-FileType", filepath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        output = result.stdout
        for line in output.splitlines():
            if line.startswith("File Type"):
                return line.split(":", 1)[1].strip()
    except Exception as e:
        print(f"Error running exiftool on {filepath}: {e}")
    return None


def process_path(path, changed_dir, processed_dir):
    """Process a single directory path (non-recursive)."""
    global total_scanned, changed_to_webp, not_changed

    if not os.path.isdir(path):
        print(f"Skipping: {path} (not a directory)")
        return

    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)

        if not os.path.isfile(full_path):
            continue  # skip folders

        total_scanned += 1

        file_type = run_exiftool(full_path)

        # Accept both WEBP and Extended WEBP
        is_webp = file_type in ("WEBP", "Extended WEBP")

        if is_webp:
            base, ext = os.path.splitext(entry)

            # Only clone if extension is NOT already .webp
            if ext.lower() != ".webp":
                new_name = base + ".webp"
                new_path = os.path.join(changed_dir, new_name)

                print(f"[+] WEBP detected ({file_type}): {entry}")
                print(f"    Creating copy as: {new_name}")

                try:
                    shutil.copy2(full_path, new_path)
                    print(f"    Copy successful.")
                    changed_to_webp += 1

                    # Move original JPG/JPEG → processed/
                    if ext.lower() in (".jpg", ".jpeg"):
                        processed_target = os.path.join(processed_dir, entry)
                        shutil.move(full_path, processed_target)
                        print(f"    Moved original JPG to processed/: {entry}")
                    else:
                        print(f"    Original file is not JPG, leaving in place.")

                except Exception as e:
                    print(f"    Error copying file: {e}")
                    not_changed += 1
            else:
                print(f"[=] Already .webp: {entry}")
                not_changed += 1

        else:
            print(f"[-] Not WEBP: {entry} ({file_type})")
            not_changed += 1


def main():
    global total_scanned, changed_to_webp, not_changed

    if len(sys.argv) < 2:
        print("Usage: python script.py <path1,path2,path3>")
        sys.exit(1)

    input_paths = sys.argv[1]
    paths = [os.path.abspath(p.strip()) for p in input_paths.split(",")]

    # Create folders where the script is executed
    script_cwd = os.getcwd()
    changed_dir = os.path.join(script_cwd, "changed")
    processed_dir = os.path.join(script_cwd, "processed")

    os.makedirs(changed_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    for path in paths:
        process_path(path, changed_dir, processed_dir)

    # Print summary
    print("\n=== Summary ===")
    print(f"Total files scanned: {total_scanned}")
    print(f"Files changed to WEBP: {changed_to_webp}")
    print(f"Files that were not changed: {not_changed}")


if __name__ == "__main__":
    main()