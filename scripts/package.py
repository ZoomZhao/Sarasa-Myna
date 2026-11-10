#!/usr/bin/env python3
"""Create a release ZIP containing installable fonts, notices and source."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from build import ROOT, FAMILY, VERSION


def main():
    reports = json.loads((ROOT / "dist/validation-report.json").read_text())
    if len(reports) != 4 or any(report["status"] != "passed" for report in reports):
        raise ValueError("Four successful style validations are required")
    for report in reports:
        font = ROOT / "dist" / f"{FAMILY}-{report['style']}.ttf"
        if hashlib.sha256(font.read_bytes()).hexdigest() != report["sha256"]:
            raise ValueError(f"Font changed after validation: {font.name}")
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "validation").mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "dist/preview.png", ROOT / "assets/preview.png")
    for name in ("build-report.json", "validation-report.json"):
        shutil.copyfile(ROOT / "dist" / name, ROOT / "validation" / name)
    output = ROOT / f"{FAMILY}-v{VERSION}.zip"
    members = {}
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "requirements.txt", ".gitignore"):
        members[name] = ROOT / name
    for directory in ("scripts", "licenses", ".github", "assets", "validation"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                members[path.relative_to(ROOT).as_posix()] = path
    for path in (ROOT / "dist").glob("*.ttf"):
        members[f"fonts/{path.name}"] = path
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n" for name, path in sorted(members.items()))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(members.items()):
            info = zipfile.ZipInfo(f"{FAMILY}-v{VERSION}/{name}", (2026, 11, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo(f"{FAMILY}-v{VERSION}/SHA256SUMS.txt", (2026, 11, 10, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, checksums.encode())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    print(json.dumps({"file": str(output), "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "members": len(members) + 1}))


if __name__ == "__main__":
    main()
