#!/usr/bin/env python3
"""Download pinned, checksum-verified public upstream release assets."""
import hashlib
import io
from pathlib import Path
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ("Myna-v2.0.0-beta.zip", "https://github.com/sayyadirfanali/Myna/releases/download/v2.0.0.0-beta/Myna-v2.0.0-beta.zip", "0013ff1c868356f4dbcb9a58799a779b3c86cf2e545eafd71e3f32c38fcf8a7b"),
    ("SarasaTermSCNerd-Unhinted.ttf.tar.gz", "https://github.com/laishulu/Sarasa-Term-SC-Nerd/releases/download/v2.3.1/SarasaTermSCNerd-Unhinted.ttf.tar.gz", "7f9c12255913a41028df04622406de2c8d6e6e4118f8be1553c44e173a3f4329"),
]


def verified_bytes(name, url, expected):
    path = ROOT / "downloads" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Sarasa-Myna-build/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            content = response.read(120 * 1024 * 1024)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
        path.write_bytes(content)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"Checksum mismatch: {name}; remove it before downloading again")
    print(f"Verified {name}")
    return content


def write_member(relative, content):
    output = ROOT / "sources" / relative
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)


def main():
    myna = verified_bytes(*ASSETS[0])
    sarasa = verified_bytes(*ASSETS[1])
    # Extract named expected files only; never unpack arbitrary archive paths.
    with zipfile.ZipFile(io.BytesIO(myna)) as archive:
        for name in ["OFL.txt", "README.txt"] + [f"fonts/Myna-{style}.ttf" for style in ("Regular", "RegularItalic", "Bold", "BoldItalic")]:
            write_member(Path("myna") / name, archive.read(name))
    with tarfile.open(fileobj=io.BytesIO(sarasa), mode="r:gz") as archive:
        for style in ("Regular", "Italic", "Bold", "BoldItalic"):
            name = f"SarasaTermSCNerd-{style}.ttf"
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError(f"Expected ordinary file: {name}")
            write_member(Path("sarasa") / name, archive.extractfile(member).read())


if __name__ == "__main__":
    main()
