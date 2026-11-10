"""Build local rules, optionally refresh mirrors, and validate the published inventory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_BASE = "https://raw.githubusercontent.com/blagodaren/blgdrn-rule-sets/main/"
RETIRED_HOST = "ssc.magickvn.com"


def safe_path(root, relative, directory):
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative:
        raise ValueError(f"Unsafe path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to((root / directory).resolve()):
        raise ValueError(f"Path must be inside {directory}/: {relative}")
    return path


def load_manifest(root):
    manifest = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not isinstance(manifest.get("sources"), list):
        raise ValueError("Expected sources.json version 1 and a sources array")
    seen = set()
    for entry in manifest["sources"]:
        output = entry["output"]
        safe_path(root, output, "ruleset")
        if output in seen:
            raise ValueError(f"Duplicate output: {output}")
        seen.add(output)
        behavior, format_ = entry["behavior"], entry["format"]
        if (behavior, format_) not in {("domain", "mrs"), ("ipcidr", "mrs"), ("classical", "yaml")}:
            raise ValueError(f"Unsupported behavior/format: {output}")
        if not output.endswith("." + format_):
            raise ValueError(f"Output extension differs from format: {output}")
        if "legacy_literal_domains" in entry:
            literals = entry["legacy_literal_domains"]
            if (entry["mode"], behavior, format_) != ("static", "domain", "mrs"):
                raise ValueError(f"Legacy literal domains require a static domain MRS: {output}")
            if (not isinstance(literals, list) or not literals
                    or any(not isinstance(value, str) or not value or value != value.strip()
                           or "\n" in value or "\r" in value for value in literals)
                    or len(set(literals)) != len(literals)):
                raise ValueError(f"Invalid legacy literal domain allowlist: {output}")
        if entry["mode"] == "static":
            safe_path(root, entry["source"], "sources")
            if "url" in entry:
                raise ValueError(f"Static entry cannot have a download URL: {output}")
        elif entry["mode"] == "mirror":
            url = urllib.parse.urlparse(entry["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError(f"Mirror must have a public HTTPS URL: {output}")
            if url.hostname == RETIRED_HOST or url.hostname.endswith("." + RETIRED_HOST):
                raise ValueError(f"Retired upstream cannot be a mirror: {output}")
            if "source" in entry:
                raise ValueError(f"Mirror entry cannot have a local source: {output}")
        else:
            raise ValueError(f"Unknown source mode: {entry['mode']}")
    if not seen:
        raise ValueError("Empty manifest")
    return manifest["sources"]


def check_domain(value):
    if value.startswith("+."):
        name = value[2:]
    elif value.startswith("."):
        name = value[1:]
    else:
        name = value
    name = name.removesuffix(".")
    if not name or len(name) > 253 or any(c.isspace() for c in name):
        raise ValueError(f"Invalid domain: {value}")
    if any(c in name for c in "/,:#[]{}'\"+\\"):
        raise ValueError(f"Invalid domain: {value}")
    if any(not label or len(label) > 63 for label in name.split(".")):
        raise ValueError(f"Invalid domain: {value}")
    if any("*" in label and label != "*" for label in name.split(".")):
        raise ValueError(f"Wildcard must occupy an entire domain label: {value}")
    if not re.fullmatch(r"[\w.*-]+", name, re.UNICODE):
        raise ValueError(f"Invalid domain: {value}")


def text_rules(path, behavior, legacy_literal_domains=()):
    rules = []
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            if behavior == "ipcidr":
                ipaddress.ip_network(value, strict=True)
            elif value not in legacy_literal_domains:
                check_domain(value)
        except ValueError as error:
            raise ValueError(f"{path}:{number}: {error}") from error
        rules.append(value)
    if not rules:
        raise ValueError(f"Empty rules: {path}")
    return rules


def validate_yaml(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or set(data) != {"payload"}:
        raise ValueError(f"Expected a YAML object containing only payload: {path}")
    payload = data["payload"]
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Expected a nonempty payload list: {path}")
    for number, rule in enumerate(payload, 1):
        if not isinstance(rule, str):
            raise ValueError(f"{path} payload {number}: expected a string")
        parts = [value.strip() for value in rule.split(",")]
        kind = parts[0]
        if kind in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}:
            if len(parts) != 2 or not parts[1]:
                raise ValueError(f"{path} payload {number}: invalid {kind}")
            check_domain(parts[1])
        elif kind in {"IP-CIDR", "IP-CIDR6"}:
            if len(parts) not in {2, 3} or (len(parts) == 3 and parts[2] != "no-resolve"):
                raise ValueError(f"{path} payload {number}: invalid IP rule")
            network = ipaddress.ip_network(parts[1], strict=True)
            if kind == "IP-CIDR6" and network.version != 6:
                raise ValueError(f"{path} payload {number}: IP-CIDR6 requires IPv6")
        else:
            raise ValueError(f"{path} payload {number}: unsupported classical type {kind}")
    return len(payload)


def convert(mihomo, behavior, format_, source, target):
    result = subprocess.run(
        [str(mihomo), "convert-ruleset", behavior, format_, str(source), str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode:
        raise ValueError(f"Mihomo rejected {source}: {(result.stderr or result.stdout).strip()}")
    if "skip invalid" in (result.stdout + result.stderr).lower():
        raise ValueError(f"Mihomo skipped invalid rules in {source}: {(result.stdout + result.stderr).strip()}")
    if not target.is_file() or not target.stat().st_size:
        raise ValueError(f"Mihomo produced an empty output: {source}")


def validate_output(entry, path, mihomo, scratch):
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"Missing or empty output: {path}")
    if entry["format"] == "yaml":
        return validate_yaml(path)
    decoded = scratch / (path.name + ".decoded.list")
    convert(mihomo, entry["behavior"], "mrs", path, decoded)
    return len(text_rules(decoded, entry["behavior"], entry.get("legacy_literal_domains", ())))


class UpstreamRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        host = parsed.hostname or ""
        if host == RETIRED_HOST or host.endswith("." + RETIRED_HOST):
            raise ValueError("Mirror redirected to retired upstream")
        if parsed.scheme != "https":
            raise ValueError("Mirror redirected away from HTTPS")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def download(url, target):
    opener = urllib.request.build_opener(UpstreamRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "blgdrn-rule-sets/1"})
    for attempt in range(3):
        try:
            with opener.open(request, timeout=60) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
            return
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def static_output(entry, root, destination, mihomo):
    source = safe_path(root, entry["source"], "sources")
    if entry["format"] == "yaml":
        validate_yaml(source)
        shutil.copyfile(source, destination)
    else:
        text_rules(source, entry["behavior"], entry.get("legacy_literal_domains", ()))
        convert(mihomo, entry["behavior"], "text", source, destination)


def validate_providers(root, entries):
    inventory = {entry["output"]: entry for entry in entries}
    for filename in ("rule-providers.yaml", "rule-providers-legacy.yaml"):
        path = root / filename
        if not path.exists() and filename.endswith("-legacy.yaml"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("rule-providers"), dict):
            raise ValueError(f"Missing rule-providers mapping: {filename}")
        cache_paths = set()
        for name, provider in data["rule-providers"].items():
            url = provider.get("url", "")
            if provider.get("type") != "http" or not url.startswith(REPOSITORY_BASE):
                raise ValueError(f"{filename}: {name} must use this repository over HTTP")
            output = url.removeprefix(REPOSITORY_BASE)
            entry = inventory.get(output)
            if not entry:
                raise ValueError(f"{filename}: {name} references an unmanaged file: {output}")
            if any(provider.get(key) != entry[key] for key in ("behavior", "format")):
                raise ValueError(f"{filename}: {name} behavior/format does not match {output}")
            cache_path = provider.get("path")
            if not cache_path or cache_path in cache_paths:
                raise ValueError(f"{filename}: {name} needs a unique cache path")
            cache_paths.add(cache_path)


def build(root, mihomo, refresh=False):
    entries = load_manifest(root)
    validate_providers(root, entries)
    with tempfile.TemporaryDirectory(prefix="rules-build-") as temp:
        stage = Path(temp)
        pending = {}
        downloads = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for index, entry in enumerate(entries):
                target = stage / f"{index}-{Path(entry['output']).name}"
                if entry["mode"] == "static":
                    static_output(entry, root, target, mihomo)
                    pending[entry["output"]] = target
                elif refresh:
                    downloads.append((entry, target, pool.submit(download, entry["url"], target)))
            for entry, target, future in downloads:
                future.result()
                pending[entry["output"]] = target
        for entry in entries:
            path = pending.get(entry["output"], root / entry["output"])
            count = validate_output(entry, path, mihomo, stage)
            print(f"OK {entry['output']}: {count} rules ({entry['mode']})", flush=True)
        # Outputs are untouched until every download and validation succeeds.
        changed = 0
        for relative, staged in pending.items():
            output = safe_path(root, relative, "ruleset")
            if output.exists() and output.read_bytes() == staged.read_bytes():
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".rules-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(staged.read_bytes())
            try:
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
            changed += 1
        print(f"Validated {len(entries)} outputs; updated {changed} files.")


def validate(root, mihomo):
    entries = load_manifest(root)
    validate_providers(root, entries)
    managed = {entry["output"] for entry in entries}
    actual = {path.relative_to(root).as_posix() for path in (root / "ruleset").iterdir()
              if path.suffix in {".mrs", ".yaml"}}
    if actual != managed:
        raise ValueError(f"Inventory mismatch: unmanaged={sorted(actual - managed)}, missing={sorted(managed - actual)}")
    with tempfile.TemporaryDirectory(prefix="rules-validate-") as temp:
        scratch = Path(temp)
        for index, entry in enumerate(entries):
            output = root / entry["output"]
            count = validate_output(entry, output, mihomo, scratch)
            if entry["mode"] == "static":
                compiled = scratch / f"{index}-rebuilt.{entry['format']}"
                static_output(entry, root, compiled, mihomo)
                if output.read_bytes() != compiled.read_bytes():
                    raise ValueError(f"Static output is stale; run build: {entry['output']}")
            print(f"OK {entry['output']}: {count} rules", flush=True)
    print(f"All {len(entries)} outputs and provider fragments are valid.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--mihomo", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true", help="Refresh mirror entries during build")
    args = parser.parse_args()
    if args.refresh and args.command != "build":
        parser.error("--refresh is supported only with build")
    try:
        if args.command == "build":
            build(ROOT, args.mihomo.resolve(), args.refresh)
        else:
            validate(ROOT, args.mihomo.resolve())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
