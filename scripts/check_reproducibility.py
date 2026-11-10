#!/usr/bin/env python3
"""Compare newly built fonts to the committed release fingerprints."""
import hashlib
import json

from build import ROOT


def main():
    reports = json.loads((ROOT / "validation/build-report.json").read_text())
    if len(reports) != 4:
        raise ValueError("Expected four reference release fingerprints")
    for report in reports:
        path = ROOT / "dist" / report["file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != report["sha256"]:
            raise ValueError(f"Reproducibility mismatch: {path.name}: {actual}")
        print(f"Reproduced {path.name}: {actual}")


if __name__ == "__main__":
    main()
