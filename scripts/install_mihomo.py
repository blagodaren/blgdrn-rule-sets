"""Download the pinned converter used by the router, verifying the release SHA256."""
import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import platform
import urllib.request
import zipfile

VERSION = "1.19.33"
ASSETS = {
    "Linux": ("mihomo-linux-amd64-compatible-v1.19.33.gz",
              "386508bfb1c72c43b6a0eda73708ecdce82546581b0ebcb16366c53757c622b6"),
    "Windows": ("mihomo-windows-amd64-compatible-v1.19.33.zip",
                "7aaf636a4f2172dcd8ec34ac4f52797b059195e5afd6409508c963e545f8864d"),
}


def install(directory: Path) -> Path:
    system = platform.system()
    if system not in ASSETS or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("This installer supports Windows/Linux x86_64 only")
    name, expected = ASSETS[system]
    url = f"https://github.com/MetaCubeX/mihomo/releases/download/v{VERSION}/{name}"
    request = urllib.request.Request(url, headers={"User-Agent": "blgdrn-rule-sets"})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = response.read()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {name}: {actual}")
    if system == "Windows":
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            executables = [entry for entry in zipped.namelist() if entry.endswith(".exe")]
            if len(executables) != 1:
                raise ValueError("Expected exactly one executable in Mihomo archive")
            binary = zipped.read(executables[0])
    else:
        binary = gzip.decompress(archive)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ("mihomo.exe" if system == "Windows" else "mihomo")
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(binary)
    if system == "Linux":
        temporary.chmod(0o755)
    os.replace(temporary, destination)
    return destination.resolve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".tools"))
    args = parser.parse_args()
    print(install(args.directory))
