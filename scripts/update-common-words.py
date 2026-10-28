#!/usr/bin/env python3
"""Rebuild the common-word list from SCOWL, the English Speller Database.

Output: engine/src/mcp_privacy_guard/data/common_words.txt.

    git clone --depth 1 --branch v2 https://github.com/en-wl/wordlist.git /tmp/wordlist
    scripts/update-common-words.py /tmp/wordlist

It reads `data/scowl-pre.txt` and `Copyright` of the checkout as text; nothing of it is run.
Kept: lower-case headwords and inflections of US spelling, three letters or more, no
abbreviations and no proper nouns, from size 35 (the smallest size of the database).
The networking terms are added.
The SCOWL copyright notice heads the file, as its licence requires.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SIZE = 35
NETWORK_TERMS = "inside outside trust untrust dmz web test prod dev lan wan mgmt".split()
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "engine" / "src" / "mcp_privacy_guard" / "data" / "common_words.txt"


LINE = re.compile(r"(\d+)[^:]*: (?:([^:<]*): )?(\S+) <([^>]*)>(.*)$")


def headwords(data: Path, size: int) -> set[str]:
    """Words of US spelling up to `size`: headwords and the inflections listed after them."""
    words: set[str] = set()
    for line in data.read_text(encoding="utf-8").splitlines():
        match = LINE.match(line)
        if match is None or int(match.group(1)) > size:
            continue
        level, codes, word, flags, tail = match.groups()
        if codes is not None and not re.search(r"\bA\b", codes):  # spelling codes: US only
            continue
        if "upper" in flags or "abbr" in flags:
            continue
        tail = re.sub(r"#.*$|\{[^}]*\}", "", tail)  # a comment and a gloss
        forms = [] if word == "-" else [word]
        forms += re.findall(r"[A-Za-z']+", tail)  # inflections, also the irregular (was | wast)
        words.update(form for form in forms if re.fullmatch(r"[a-z]{3,}", form))
    return words


def main(checkout: Path) -> None:
    notice = (checkout / "Copyright").read_text(encoding="utf-8").split("\n===")[0].strip()
    words = sorted(headwords(checkout / "data" / "scowl-pre.txt", SIZE) | set(NETWORK_TERMS))
    header = [
        "# Common English words: SCOWL / ESDB (https://github.com/en-wl/wordlist), size "
        f"{SIZE}, US spelling.",
        "# Built by scripts/update-common-words.py, plus the networking terms.",
        "# Notice of the source:",
        "#",
        *(f"# {line}".rstrip() for line in notice.splitlines()),
    ]
    OUT.write_text("\n".join([*header, *words]) + "\n", encoding="utf-8")
    print(f"{len(words)} words written to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
