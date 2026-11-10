#!/usr/bin/env python3
"""Build a Myna-first Unicode union with a scaled Sarasa Nerd fallback."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.merge import Merger, Options as MergeOptions
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import ScalerVisitor

ROOT = Path(__file__).resolve().parents[1]
STYLES = {"Regular": "Regular", "Italic": "RegularItalic", "Bold": "Bold", "BoldItalic": "BoldItalic"}
FAMILY = "Sarasa-Myna"
VERSION = "0.1.0"
TIMESTAMP = 3877113600  # 2026-11-10 00:00:00 UTC in OpenType epoch
CELL = 486
EXCLUDED_FALLBACK = set(range(0xE200, 0xE2AA))  # Font Awesome Extension provenance gap


def remove_tables(font, tags):
    for tag in tags:
        if tag in font:
            del font[tag]


def prepare_primary(path: Path) -> TTFont:
    font = TTFont(path, recalcTimestamp=False)
    remove_tables(font, ("BASE", "FFTM", "DSIG"))
    return font


def prepare_fallback(path: Path, primary_cmap: dict) -> TTFont:
    font = TTFont(path, recalcTimestamp=False)
    # The upstream regular/bold GSUB has malformed offsets. Do not carry it
    # into the output, or preserve different fallback substitutions per style.
    # Myna's GSUB is retained, including calt, ccmp, and frac.
    remove_tables(font, ("GSUB", "BASE", "FFTM", "DSIG", "PfEd", "hdmx", "vhea", "vmtx"))
    codepoints = set(font.getBestCmap()) - set(primary_cmap) - EXCLUDED_FALLBACK
    options = subset.Options()
    options.layout_features = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recalc_average_width = False
    options.recalc_timestamp = False
    options.hinting = False
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    # Unicode bidirectional closure may re-add mirrored codepoints. Never
    # let this automatic closure override a Myna codepoint in the merger.
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp in codepoints}
    # Preserve Myna exactly; scale all donor geometry and layout from 500 to
    # 486 units/cell. Restoring UPM keeps the two fonts in the same coordinate
    # system and produces precisely 972 units for full-width characters.
    ScalerVisitor(CELL / 500).visit(font)
    font["head"].unitsPerEm = 1000
    return font


def set_names(font: TTFont, style: str, copyright_text: str):
    subfamily = {"BoldItalic": "Bold Italic"}.get(style, style)
    full = f"{FAMILY} {subfamily}"
    names = {
        0: copyright_text,
        1: FAMILY,
        2: subfamily,
        3: f"{VERSION};SarasaMyna;{FAMILY}-{style}",
        4: full,
        5: f"Version {VERSION}",
        6: f"{FAMILY}-{style}",
        7: "Independent modified font; no endorsement by upstream authors.",
        8: "Sarasa-Myna contributors",
        9: "Myna, Sarasa Gothic, Sarasa Term SC Nerd and Nerd Fonts contributors",
        10: "Myna-first Unicode union; Sarasa fallback scaled to exact 2:1 CJK cells. See bundled licenses and README.",
        13: "Font software: SIL Open Font License 1.1. Included third-party icon components retain their original licenses. See licenses/ and THIRD_PARTY_NOTICES.md.",
        14: "https://openfontlicense.org/open-font-license-official-text/",
        16: FAMILY,
        17: subfamily,
    }
    font["name"].names = []
    for name_id, value in names.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)


def finish(font: TTFont, primary: TTFont, style: str, copyright_text: str):
    set_names(font, style, copyright_text)
    remove_tables(font, ("DSIG", "FFTM", "BASE", "PfEd", "hdmx", "vhea", "vmtx"))
    font["head"].created = TIMESTAMP
    font["head"].modified = TIMESTAMP
    font["head"].fontRevision = 0.100
    font.recalcTimestamp = False
    font["post"].isFixedPitch = 1
    # Upstream Myna's right-slanted outlines have a left-slant +12 metadata
    # sign. Correct the metadata, not the contours.
    font["post"].italicAngle = -12 if "Italic" in style else 0
    font["hhea"].caretSlopeRise = 100
    font["hhea"].caretSlopeRun = 21 if "Italic" in style else 0
    os2 = font["OS/2"]
    os2.usWeightClass = 700 if "Bold" in style else 400
    os2.usWidthClass = 5
    os2.fsType = 0
    os2.xAvgCharWidth = CELL
    os2.panose.bProportion = 9
    # Keep a compact, identical default line box across every style. Tall
    # accents may extend into neighbouring line boxes; Windows clipping bounds
    # are calculated separately from every resulting glyph below.
    font["hhea"].ascent = os2.sTypoAscender = 984
    font["hhea"].descent = os2.sTypoDescender = -277
    font["hhea"].lineGap = os2.sTypoLineGap = 0
    os2.fsSelection = (1 << 7) | (1 if "Italic" in style else 0) | ((1 << 5) if "Bold" in style else 0)
    if style == "Regular":
        os2.fsSelection |= 1 << 6
    font["head"].macStyle = (1 if "Bold" in style else 0) | (2 if "Italic" in style else 0)
    glyf = font["glyf"]
    ymax, ymin = 984, -277
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        glyph.recalcBounds(glyf)
        if hasattr(glyph, "yMax"):
            ymax = max(ymax, glyph.yMax)
            ymin = min(ymin, glyph.yMin)
    os2.usWinAscent = ymax
    os2.usWinDescent = -ymin
    os2.recalcUnicodeRanges(font)
    os2.recalcCodePageRanges(font)


def build_style(style: str, output_dir: Path) -> dict:
    myna_path = ROOT / "sources/myna/fonts" / f"Myna-{STYLES[style]}.ttf"
    sarasa_path = ROOT / "sources/sarasa" / f"SarasaTermSCNerd-{style}.ttf"
    primary = prepare_primary(myna_path)
    original_fallback = TTFont(sarasa_path, lazy=True)
    copyright_text = "\n".join(dict.fromkeys([
        primary["name"].getDebugName(0) or "",
        original_fallback["name"].getDebugName(0) or "",
        "Modified 2026 for Sarasa-Myna. Original author names are acknowledgments only.",
    ]))
    expected = set(primary.getBestCmap()) | (set(original_fallback.getBestCmap()) - EXCLUDED_FALLBACK)
    fallback = prepare_fallback(sarasa_path, primary.getBestCmap())
    work = ROOT / "build" / style
    work.mkdir(parents=True, exist_ok=True)
    primary.save(work / "primary.ttf")
    fallback.save(work / "fallback.ttf")
    options = MergeOptions()
    options.drop_tables = ["BASE", "FFTM", "DSIG", "PfEd", "hdmx", "vhea", "vmtx"]
    font = Merger(options).merge([str(work / "primary.ttf"), str(work / "fallback.ttf")])
    finish(font, primary, style, copyright_text)
    assert set(font.getBestCmap()) == expected
    assert len(font.getGlyphOrder()) < 65535
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{FAMILY}-{style}.ttf"
    font.save(output)
    check = TTFont(output, checkChecksums=2, recalcTimestamp=False)
    for tag in check.keys()[1:]:
        check[tag]  # full table decoding
    report = {
        "file": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "codepoints": len(expected),
        "myna_codepoints": len(primary.getBestCmap()),
        "fallback_codepoints": len(expected) - len(primary.getBestCmap()),
        "glyphs": len(check.getGlyphOrder()),
        "advance_widths": dict(sorted(Counter(check["hmtx"].metrics[g][0] for g in check.getBestCmap().values()).items())),
        "line_metrics": [check["hhea"].ascent, check["hhea"].descent, check["hhea"].lineGap],
        "windows_clipping_bounds": [check["OS/2"].usWinAscent, check["OS/2"].usWinDescent],
    }
    print(json.dumps(report), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--styles", nargs="+", choices=STYLES, default=list(STYLES))
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    reports = [build_style(style, args.output) for style in args.styles]
    (args.output / "build-report.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
