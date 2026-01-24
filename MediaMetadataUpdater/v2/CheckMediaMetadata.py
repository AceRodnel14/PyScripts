import os
import re
import json
import argparse
from datetime import datetime

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Button, ScrollView
from textual.containers import Vertical, Horizontal

# Pattern loading

def load_external_patterns(cwd: str):
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
        print(f"[red]Error loading pattern.json:[/red] {e}")
        return None


# Built-in main patterns (used if pattern.json is missing)
BUILTIN_PATTERNS = [
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

# Built-in fallback patterns
FALLBACK_SPACE = re.compile(r'^(\d{2})(\d{2})(\d{2})\s+.*')
FALLBACK_DASH = re.compile(r'^(\d{2})(\d{2})(\d{2})-.*')


# Pattern matching logic

def classify_filename(fname: str, patterns):
    """Return (kind, info_dict) where kind is 'main', 'fallback', or 'none'."""
    # Try main patterns
    for pat in patterns:
        m = pat["regex"].match(fname)
        if m:
            ts = m.group(pat["group"])
            # We don't care if parsing fails here for the browser; just show the raw timestamp
            return "main", {
                "filename": fname,
                "pattern": pat["regex"].pattern,
                "timestamp": ts,
            }

    # Try fallback 1
    m1 = FALLBACK_SPACE.match(fname)
    if m1:
        yy, mm, dd = m1.groups()
        try:
            datetime(int("20" + yy), int(mm), int(dd))
            ts = f"20{yy}-{mm}-{dd}"
            return "fallback", {
                "filename": fname,
                "pattern": "YYMMDD<space>",
                "timestamp": ts,
            }
        except ValueError:
            pass

    # Try fallback 2
    m2 = FALLBACK_DASH.match(fname)
    if m2:
        yy, mm, dd = m2.groups()
        try:
            datetime(int("20" + yy), int(mm), int(dd))
            ts = f"20{yy}-{mm}-{dd}"
            return "fallback", {
                "filename": fname,
                "pattern": "YYMMDD-",
                "timestamp": ts,
            }
        except ValueError:
            pass

    # No match
    return "none", {
        "filename": fname,
        "pattern": None,
        "timestamp": None,
    }


# Arg parsing

def parse_args():
    parser = argparse.ArgumentParser(description="Pattern Browser (read-only, non-recursive)")
    parser.add_argument(
        "--dir",
        required=True,
        help="Comma-separated list of directories to scan (non-recursive)"
    )
    return parser.parse_args()


# Textual App

class PatternBrowser(App):
    TITLE = "Pattern Browser"
    SUB_TITLE = "Pattern.json + built-in patterns (read-only)"

    def __init__(self, results, summary, **kwargs):
        super().__init__(**kwargs)
        self.results = results
        self.summary = summary

    def compose(self) -> ComposeResult:
        yield Header()

        yield Vertical(
            Static("", id="summary_box"),
            Horizontal(
                Button("Show matched files", id="btn_matched"),
                Button("Show not matched files", id="btn_notmatched"),
                id="buttons_row"
            ),
            ScrollView(Static("", id="output_box"), id="scroll_area"),
        )

        yield Footer()

    def on_mount(self):
        # Set summary text
        summary_box = self.query_one("#summary_box", Static)
        s = self.summary
        summary_text = (
            f"[b]Pattern Browser Summary[/b]\n"
            f"Total files: {s['total']}\n"
            f"Matched (main + fallback): {s['matched_total']}\n"
            f"  - Main matches: {s['main']}\n"
            f"  - Fallback matches: {s['fallback']}\n"
            f"Not matched: {s['none']}\n"
        )
        summary_box.update(summary_text)

    def on_button_pressed(self, event: Button.Pressed):
        output_box = self.query_one("#output_box", Static)

        if event.button.id == "btn_matched":
            lines = []
            for item in self.results:
                if item["kind"] in ("main", "fallback"):
                    color = "green" if item["kind"] == "main" else "yellow"
                    lines.append(
                        f"[{color}]{item['filename']}[/{color}]\n"
                        f"[{color}]--- matched pattern:[/{color}] {item['pattern']}\n"
                        f"[{color}]--- extracted timestamp:[/{color}] {item['timestamp']}\n"
                    )
            if not lines:
                lines = ["[yellow]No matched files.[/yellow]\n"]
            output_box.update("\n".join(lines))

        elif event.button.id == "btn_notmatched":
            lines = []
            for item in self.results:
                if item["kind"] == "none":
                    lines.append(
                        f"[red]{item['filename']}[/red]\n"
                        f"[red]--- no pattern matched[/red]\n"
                    )
            if not lines:
                lines = ["[green]All files matched some pattern.[/green]\n"]
            output_box.update("\n".join(lines))


# Main entry

def main():
    args = parse_args()
    cwd = os.getcwd()

    # Directories to scan (non-recursive)
    folder_list = [os.path.abspath(p.strip()) for p in args.dir.split(",") if p.strip()]

    # Load patterns
    external = load_external_patterns(cwd)
    patterns = external if external else BUILTIN_PATTERNS

    # Scan files (non-recursive)
    results = []
    main_count = 0
    fallback_count = 0
    none_count = 0
    total_files = 0

    for folder in folder_list:
        if not os.path.isdir(folder):
            print(f"[red]Directory not found:[/red] {folder}")
            continue

        for entry in os.listdir(folder):
            fpath = os.path.join(folder, entry)
            if os.path.isdir(fpath):
                continue

            kind, info = classify_filename(entry, patterns)
            info["kind"] = kind
            results.append(info)

            total_files += 1
            if kind == "main":
                main_count += 1
            elif kind == "fallback":
                fallback_count += 1
            else:
                none_count += 1

    summary = {
        "total": total_files,
        "main": main_count,
        "fallback": fallback_count,
        "matched_total": main_count + fallback_count,
        "none": none_count,
    }

    app = PatternBrowser(results=results, summary=summary)
    app.run()


if __name__ == "__main__":
    main()