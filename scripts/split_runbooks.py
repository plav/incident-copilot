"""Split a pasted export of several runbooks into one clean .md file each.

Usage:
    python -m scripts.split_runbooks private/rovo-export.txt private/runbooks

Fixes common copy-paste damage from AI tools and rendered pages:
- stray ``` code fences and leftover HTML-like tags
- section headings that lost their "## " marker
- a new runbook starting on the line straight after the previous one
"""
import re
import sys
from pathlib import Path

SECTIONS = [
    "Symptoms", "Likely Causes", "Diagnostic Steps",
    "Resolution Steps", "Escalation", "Source Tickets",
]
SECTION_RE = re.compile(rf"^#{{0,3}}\s*({'|'.join(SECTIONS)})\s*:?\s*$", re.IGNORECASE)


def clean(text: str) -> str:
    text = re.sub(r"</?(line|uuid)>", "", text, flags=re.IGNORECASE)    # stray tags
    text = re.sub(r"^\s*```[a-z]*\s*$", "", text, flags=re.MULTILINE)  # code fences
    return text


def split(text: str) -> list[tuple[str, str]]:
    runbooks: list[tuple[str, list[str]]] = []
    for line in clean(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            runbooks.append((stripped[2:].strip(), []))
            continue
        if not runbooks:
            continue  # ignore anything before the first title
        match = SECTION_RE.match(stripped)
        if match:
            canonical = next(s for s in SECTIONS if s.lower() == match.group(1).lower())
            runbooks[-1][1].extend(["", f"## {canonical}"])
        else:
            runbooks[-1][1].append(line.rstrip())
    out = []
    for title, lines in runbooks:
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        out.append((title, f"# {title}\n\n{body}\n"))
    return out


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    runbooks = split(source.read_text(encoding="utf-8"))
    if not runbooks:
        print("No runbooks found: each one must start with a '# Title' line.")
        return 1
    for title, content in runbooks:
        path = out_dir / f"{slugify(title)}.md"
        path.write_text(content, encoding="utf-8")
        found = [s for s in SECTIONS if f"## {s}" in content]
        missing = [s for s in SECTIONS[:5] if s not in found]
        status = "OK" if not missing else f"MISSING: {', '.join(missing)}"
        print(f"  {path}  ({len(found)} sections)  {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
