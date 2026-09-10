"""Guard reviewed English release text against accidental non-English scripts.

This is a script-level regression guard, not an automatic proof of language.
Scientific Greek symbols, Latin identifiers and Unicode punctuation are allowed.
Binary manuscript figures are reviewed separately and preserved byte-for-byte.
"""
import gzip
import json
from pathlib import Path
import re

NON_ENGLISH_SCRIPT = re.compile(
    r"[\u0400-\u052f\u0590-\u08ff\u0900-\u109f\u1100-\u11ff"
    r"\u3040-\u30ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff"
    r"\uac00-\ud7af\uf900-\ufaff]"
)
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".js", ".mjs", ".css", ".html",
                 ".tsv", ".csv", ".svg", ".yml", ".yaml", ".toml", ".sh"}
TEXT_NAMES = {"LICENSE", ".gitignore", ".gitattributes"}


def _json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)


def check_english_release(files: list[Path]) -> int:
    checked = 0
    for path in files:
        compressed_text = path.suffix == ".gz" and Path(path.stem).suffix in TEXT_SUFFIXES
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES and not compressed_text:
            continue
        checked += 1
        opener = gzip.open if compressed_text else open
        with opener(path, "rt", encoding="utf-8") as stream:
            if path.suffix == ".json":
                strings = _json_strings(json.load(stream))
            else:
                strings = stream
            if any(NON_ENGLISH_SCRIPT.search(value) for value in strings):
                raise ValueError(f"Non-English script in release text: {path.name}; review without exposing content")
    return checked
