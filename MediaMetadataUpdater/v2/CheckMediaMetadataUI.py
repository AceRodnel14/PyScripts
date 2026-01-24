import os
import re
import json
from datetime import datetime
from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, TextArea, Button, Static, ScrollView
)
from textual.containers import Vertical
from textual.reactive import reactive


cwd = os.getcwd()

# -----------------------------
# Load external pattern.json
# -----------------------------
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


# -----------------------------
# Built-in patterns
# -----------------------------
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

# -----------------------------
# Built-in fallback patterns
# -----------------------------
fallback_space = re.compile(r'^(\d{2})(\d{2})(\d{2})\s+.*')
fallback_dash = re.compile(r'^(\d{2})(\d{2})(\d{2})-.*')


# -----------------------------
# Pattern Matching Logic
# -----------------------------
def test_filename(fname, patterns):
    # Try main patterns
    for pat in patterns:
        m = pat["regex"].match(fname)
        if m:
            ts = m.group(pat["group"])
            return (
                "green",
                f"{fname}\n"
                f"[green]--- matched pattern:[/green] {pat['regex'].pattern}\n"
                f"[green]--- extracted timestamp:[/green] {ts}\n"
            )

    # Try fallback 1
    m1 = fallback_space.match(fname)
    if m1:
        yy, mm, dd = m1.groups()
        try:
            dt = datetime(int("20" + yy), int(mm), int(dd))
            return (
                "yellow",
                f"{fname}\n"
                f"[yellow]--- matched fallback: YYMMDD<space>[/yellow]\n"
                f"[yellow]--- extracted timestamp:[/yellow] 20{yy}-{mm}-{dd}\n"
            )
        except ValueError:
            pass

    # Try fallback 2
    m2 = fallback_dash.match(fname)
    if m2:
        yy, mm, dd = m2.groups()
        try:
            dt = datetime(int("20" + yy), int(mm), int(dd))
            return (
                "yellow",
                f"{fname}\n"
                f"[yellow]--- matched fallback: YYMMDD-[/yellow]\n"
                f"[yellow]--- extracted timestamp:[/yellow] 20{yy}-{mm}-{dd}\n"
            )
        except ValueError:
            pass

    # No match
    return (
        "red",
        f"{fname}\n"
        f"[red]--- no pattern matched[/red]\n"
    )


# -----------------------------
# TUI Application
# -----------------------------
class PatternTester(App):
    CSS_PATH = None
    TITLE = "Pattern Tester"
    SUB_TITLE = "Test filename patterns with pattern.json support"

    output_text = reactive("")

    def compose(self) -> ComposeResult:
        yield Header()

        yield Vertical(
            Static("Enter filenames (one per line):"),
            TextArea(id="input_box", height=10),

            Button("Check Patterns", id="check_btn"),

            Static("Results:", id="results_label"),
            ScrollView(Static("", id="output_box"), id="scroll_area", height=20)
        )

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "check_btn":
            self.run_pattern_check()

    def run_pattern_check(self):
        input_box = self.query_one("#input_box", TextArea)
        output_box = self.query_one("#output_box", Static)

        filenames = [line.strip() for line in input_box.value.split("\n") if line.strip()]

        # Load patterns
        external = load_external_patterns()
        patterns = external if external else builtin_patterns

        results = []

        for fname in filenames:
            _, text = test_filename(fname, patterns)
            results.append(text)

        output_box.update("\n".join(results))


if __name__ == "__main__":
    PatternTester().run()