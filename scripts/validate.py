#!/usr/bin/env python3
"""Verify the priority contract, 2:1 cells, shaping, and installable SFNTs."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
import uharfbuzz as hb

from build import ROOT, STYLES, EXCLUDED_FALLBACK, CELL, FAMILY


def outline(font, glyph_name, glyphset):
    # Compare actual TrueType geometry, not getGlyphSet's lsb-xMin drawing
    # adjustment: some Myna source bounding boxes are off by one unit and
    # FontTools correctly recalculates them while preserving contours/hmtx.
    coordinates, end_points, flags = font["glyf"][glyph_name].getCoordinates(font["glyf"])
    return tuple(coordinates), tuple(end_points), bytes(flags)


def shaped(path, text):
    font = hb.Font(hb.Face(path.read_bytes()))
    font.scale = (1000, 1000)
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, {"calt": True})
    return [(i.codepoint, i.cluster, p.x_advance, p.y_advance, p.x_offset, p.y_offset) for i, p in zip(buffer.glyph_infos, buffer.glyph_positions)]


def validate_style(style):
    path = ROOT / "dist" / f"{FAMILY}-{style}.ttf"
    src_path = ROOT / "sources/myna/fonts" / f"Myna-{STYLES[style]}.ttf"
    font = TTFont(path, checkChecksums=2)
    source = TTFont(src_path)
    donor = TTFont(ROOT / "sources/sarasa" / f"SarasaTermSCNerd-{style}.ttf", lazy=True)
    fallback = TTFont(ROOT / "build" / style / "fallback.ttf")
    for tag in font.keys()[1:]:
        font[tag]
    cmap, src_cmap, donor_cmap = font.getBestCmap(), source.getBestCmap(), donor.getBestCmap()
    assert set(cmap) == set(src_cmap) | (set(donor_cmap) - EXCLUDED_FALLBACK)
    assert not (set(cmap) & (EXCLUDED_FALLBACK - set(src_cmap)))
    glyphset, src_glyphset = font.getGlyphSet(), source.getGlyphSet()
    for cp, glyph_name in src_cmap.items():
        target = cmap[cp]
        assert font["hmtx"].metrics[target] == source["hmtx"].metrics[glyph_name], hex(cp)
        assert outline(font, target, glyphset) == outline(source, glyph_name, src_glyphset), hex(cp)
    # Verify every donor outline/metric against the normalized, prepared font.
    fallback_cmap, fallback_glyphset = fallback.getBestCmap(), fallback.getGlyphSet()
    checked_pairs = set()
    for cp, glyph_name in fallback_cmap.items():
        target = cmap[cp]
        pair = (glyph_name, target)
        if pair in checked_pairs:
            continue
        checked_pairs.add(pair)
        assert font["hmtx"].metrics[target] == fallback["hmtx"].metrics[glyph_name], hex(cp)
        assert outline(font, target, glyphset) == outline(fallback, glyph_name, fallback_glyphset), hex(cp)
    for cp in range(0x20, 0x7F):
        assert font["hmtx"].metrics[cmap[cp]][0] == CELL
    cjk = [cp for cp in cmap if 0x4E00 <= cp <= 0x9FFF]
    assert cjk
    assert all(font["hmtx"].metrics[cmap[cp]][0] == 2 * CELL for cp in cjk)
    assert font["name"].getDebugName(1) == FAMILY
    assert font["name"].getDebugName(6) == f"{FAMILY}-{style}"
    assert font["post"].isFixedPitch == 1
    assert font["post"].italicAngle == (-12 if "Italic" in style else 0)
    assert font["hhea"].caretSlopeRun == (21 if "Italic" in style else 0)
    assert font["head"].unitsPerEm == 1000
    assert (font["hhea"].ascent, font["hhea"].descent, font["hhea"].lineGap) == (984, -277, 0)
    assert font["OS/2"].fsSelection & (1 << 7)
    assert len(font.getGlyphOrder()) < 65535
    features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    assert {"calt", "ccmp", "frac"} <= features
    texts = ["The quick brown fox jumps over the lazy dog 0123456789", "|> := -> => != <= >= === ~= :: >>= && ||", "ÀÁÂÃÄÅ àáâãäå éèêë Çç Ññ", "1lI| 0Oo [] {} () /* +-*/", "a\u0301 e\u0300 o\u0308", "1/2 3/4 12/34"]
    for text in texts:
        first, second = shaped(src_path, text), shaped(path, text)
        assert len(first) == len(second), text
        for a, b in zip(first, second):
            assert a[1:] == b[1:], (text, a, b)
            assert outline(source, source.getGlyphName(a[0]), src_glyphset) == outline(font, font.getGlyphName(b[0]), glyphset), text
    mixed = shaped(path, "ab中文")
    assert [x[2] for x in mixed] == [CELL, CELL, 2 * CELL, 2 * CELL]
    # FreeType rasterization exercises the actual serialized file.
    display = ImageFont.truetype(str(path), 28)
    assert display.getmask("Sarasa-Myna 中文   ").getbbox()
    report = {"style": style, "status": "passed", "myna_outlines_verified": len(src_cmap), "fallback_codepoints_verified": len(fallback_cmap), "cjk_2_to_1_verified": len(cjk), "shaping_samples": len(texts), "glyphs": len(font.getGlyphOrder()), "codepoints": len(cmap), "excluded_fae_slots": len(set(donor_cmap) & EXCLUDED_FALLBACK), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(report), flush=True)
    return report


def preview():
    image = Image.new("RGB", (1380, 1230), "#121820")
    draw = ImageDraw.Draw(image)
    regular = ROOT / "dist" / "Sarasa-Myna-Regular.ttf"
    heading = ImageFont.truetype(str(regular), 47)
    subtitle = ImageFont.truetype(str(regular), 25)
    draw.text((56, 35), "Sarasa-Myna", fill="#d5f7c7", font=heading)
    draw.text((56, 101), "Myna 优先 / Sarasa 中文 + Nerd 图标 / 四种样式", fill="#b4bfcd", font=subtitle)
    for row, style in enumerate(STYLES):
        y = 178 + row * 245
        font = ImageFont.truetype(str(ROOT / "dist" / f"Sarasa-Myna-{style}.ttf"), 30)
        draw.line((56, y - 16, 1324, y - 16), fill="#344150", width=1)
        draw.text((56, y), style, fill="#8ecae6", font=font)
        draw.text((56, y + 43), "const message = \"Hello, 世界！\";  // Myna + 中文", fill="#eff3f8", font=font)
        draw.text((56, y + 85), "0Ool1I | |> := -> => != <= >= === :: >>=", fill="#eff3f8", font=font)
        draw.text((56, y + 127), "| ABCD | 中文 | 1234 | 测试 |       ", fill="#d5f7c7", font=font)
        draw.text((56, y + 169), "| 1234 | 测试 | ABCD | 中文 |  英文 486 / 中文 972", fill="#b4bfcd", font=font)
    draw.text((56, 1182), "v0.1.0 / 1000 UPM / Myna outlines unchanged / fallback scaled 97.2%", fill="#8796a8", font=ImageFont.truetype(str(regular), 20))
    image.save(ROOT / "dist" / "preview.png")


if __name__ == "__main__":
    reports = [validate_style(style) for style in STYLES]
    (ROOT / "dist" / "validation-report.json").write_text(json.dumps(reports, indent=2) + "\n")
    preview()
