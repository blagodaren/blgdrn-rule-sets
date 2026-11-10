"""Replace only rule-providers in a private Mihomo config; never upload it."""

import argparse
from pathlib import Path
import re

import yaml


def migrate(text: str, fragment: str) -> str:
    original = yaml.safe_load(text)
    replacement = yaml.safe_load(fragment)
    expected = replacement["rule-providers"]
    if set(original.get("rule-providers", {})) != set(expected):
        raise ValueError("Provider names differ from this repository's current config")
    match = re.search(r"(?m)^rule-providers:[ \t]*$", text)
    if match is None:
        raise ValueError("Expected a top-level rule-providers section")
    following = re.search(r"(?m)^[^\s#][^\n]*:", text[match.end():])
    end = match.end() + following.start() if following else len(text)
    result = text[:match.start()] + fragment.rstrip() + "\n\n" + text[end:]
    parsed = yaml.safe_load(result)
    for key in original.keys() | parsed.keys():
        if key != "rule-providers" and original.get(key) != parsed.get(key):
            raise ValueError(f"Unexpected change outside rule-providers: {key}")
    if parsed["rule-providers"] != expected:
        raise ValueError("Provider section replacement failed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error("Choose a new output file; the original is never overwritten")
    fragment = Path(__file__).resolve().parents[1] / "rule-providers.yaml"
    result = migrate(args.input.read_text(encoding="utf-8"), fragment.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print(f"Saved {args.output}; only rule-providers changed")


if __name__ == "__main__":
    main()
