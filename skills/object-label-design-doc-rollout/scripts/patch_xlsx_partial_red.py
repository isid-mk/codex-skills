#!/usr/bin/env python3
"""Copy an OOXML workbook and replace approved cell text with partial red rich text."""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
import posixpath
import re
import sys
import tempfile
from lxml import etree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def register_namespaces(data: bytes) -> None:
    # Kept for callers that used the previous helper API. lxml preserves the
    # source document's namespace map directly, including declarations that are
    # referenced only by mc:Ignorable.
    return None


def parse_xml(data: bytes) -> ET.Element:
    parser = ET.XMLParser(remove_blank_text=False, resolve_entities=False, huge_tree=True)
    return ET.fromstring(data, parser=parser)


def validate_ignorable_prefixes(root: ET.Element) -> None:
    ignorable = root.get(q(MC, "Ignorable"))
    if not ignorable:
        return
    missing = [prefix for prefix in ignorable.split() if prefix not in root.nsmap]
    if missing:
        raise ValueError(f"Undeclared mc:Ignorable namespace prefixes: {', '.join(missing)}")


def serialize_xml(root: ET.Element) -> bytes:
    validate_ignorable_prefixes(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def clone(element: ET.Element | None) -> ET.Element | None:
    return copy.deepcopy(element) if element is not None else None


def style_key(rpr: ET.Element | None) -> bytes:
    return b"" if rpr is None else ET.tostring(rpr, encoding="utf-8")


def red_style(rpr: ET.Element | None) -> ET.Element:
    result = clone(rpr)
    if result is None:
        result = ET.Element(q(MAIN, "rPr"))
    for child in list(result):
        if child.tag == q(MAIN, "color"):
            result.remove(child)
    color = ET.Element(q(MAIN, "color"), {"rgb": "FFFF0000"})
    insert_before = {"sz", "u", "vertAlign", "scheme"}
    index = len(result)
    for i, child in enumerate(result):
        if child.tag.rsplit("}", 1)[-1] in insert_before:
            index = i
            break
    result.insert(index, color)
    return result


@dataclass
class StyledChar:
    text: str
    rpr: ET.Element | None


RUN_PROPERTY_ORDER = [
    "rFont", "charset", "family", "b", "i", "strike", "outline",
    "shadow", "condense", "extend", "color", "sz", "u", "vertAlign", "scheme",
]


def merged_run_properties(
    inherited: ET.Element | None, explicit: ET.Element | None
) -> ET.Element | None:
    """Materialize the effective run style without losing explicit overrides."""
    properties: dict[str, ET.Element] = {}
    extras: list[ET.Element] = []
    for source in (inherited, explicit):
        if source is None:
            continue
        for child in source:
            local_name = child.tag.rsplit("}", 1)[-1]
            copied = clone(child)
            if copied is None:
                continue
            if local_name in RUN_PROPERTY_ORDER:
                properties[local_name] = copied
            else:
                extras = [item for item in extras if item.tag != copied.tag]
                extras.append(copied)
    if not properties and not extras:
        return None
    result = ET.Element(q(MAIN, "rPr"))
    for name in RUN_PROPERTY_ORDER:
        if name in properties:
            result.append(properties[name])
    result.extend(extras)
    return result


def container_chars(
    container: ET.Element, fallback_rpr: ET.Element | None
) -> list[StyledChar]:
    chars: list[StyledChar] = []
    for child in list(container):
        if child.tag == q(MAIN, "t"):
            chars.extend(StyledChar(ch, clone(fallback_rpr)) for ch in (child.text or ""))
        elif child.tag == q(MAIN, "r"):
            rpr = child.find(q(MAIN, "rPr"))
            text = "".join(t.text or "" for t in child.findall(q(MAIN, "t")))
            effective_rpr = merged_run_properties(fallback_rpr, rpr)
            chars.extend(StyledChar(ch, clone(effective_rpr)) for ch in text)
        # Phonetic guides are intentionally ignored for an edited cell because
        # their character offsets become stale after replacement.
    return chars


def cell_chars(
    cell: ET.Element,
    shared_strings: list[ET.Element],
    fallback_rpr: ET.Element | None,
) -> list[StyledChar]:
    cell_type = cell.get("t")
    if cell_type == "s":
        value = cell.find(q(MAIN, "v"))
        if value is None or value.text is None:
            raise ValueError("Shared-string cell has no index")
        return container_chars(shared_strings[int(value.text)], fallback_rpr)
    if cell_type == "inlineStr":
        inline = cell.find(q(MAIN, "is"))
        if inline is None:
            return []
        return container_chars(inline, fallback_rpr)
    if cell_type in {"str", None}:
        value = cell.find(q(MAIN, "v"))
        return [StyledChar(ch, clone(fallback_rpr)) for ch in ((value.text or "") if value is not None else "")]
    raise ValueError(f"Unsupported text cell type: {cell_type}")


def common_affixes(old: str, new: str) -> tuple[int, int]:
    prefix = 0
    while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < len(old) - prefix
        and suffix < len(new) - prefix
        and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]
    ):
        suffix += 1
    return prefix, suffix


def find_spans(text: str, needle: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        found = text.find(needle, start)
        if found < 0:
            return spans
        spans.append((found, found + len(needle)))
        start = found + len(needle)


def selected_spans(text: str, edit: dict) -> list[tuple[int, int]]:
    old = edit["old"]
    matches = find_spans(text, old)
    occurrence = edit.get("occurrences")
    if occurrence is None:
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one match for {old!r}; found {len(matches)}")
        return matches
    if occurrence == "all":
        if not matches:
            raise ValueError(f"No matches for {old!r}")
        return matches
    if not isinstance(occurrence, list) or not occurrence:
        raise ValueError("occurrences must be 'all' or a non-empty list of 1-based indexes")
    indexes = []
    for value in occurrence:
        if not isinstance(value, int) or value < 1 or value > len(matches):
            raise ValueError(f"Invalid occurrence {value!r} for {len(matches)} matches")
        indexes.append(value - 1)
    if len(set(indexes)) != len(indexes):
        raise ValueError("Duplicate occurrence indexes are not allowed")
    return [matches[index] for index in indexes]


def replacement_chars(
    old_chars: list[StyledChar],
    old: str,
    new: str,
    red_text: str | None,
    fallback_rpr: ET.Element | None,
) -> list[StyledChar]:
    prefix, suffix = common_affixes(old, new)
    base = clone(old_chars[min(prefix, len(old_chars) - 1)].rpr) if old_chars else None
    if base is None:
        base = clone(fallback_rpr)
    red_start = 0
    red_end = len(new)
    if red_text is not None:
        red_start = new.find(red_text)
        if red_start < 0 or new.find(red_text, red_start + 1) >= 0:
            raise ValueError("red_text must occur exactly once within new")
        red_end = red_start + len(red_text)

    result: list[StyledChar] = []
    for index, character in enumerate(new):
        if index < prefix and index < len(old_chars):
            style = clone(old_chars[index].rpr)
        elif suffix and index >= len(new) - suffix:
            old_index = len(old_chars) - (len(new) - index)
            style = clone(old_chars[old_index].rpr)
        else:
            style = clone(base)
        if red_start <= index < red_end:
            if style is None:
                style = clone(fallback_rpr)
            style = red_style(style)
        result.append(StyledChar(character, style))
    return result


def apply_edit(
    chars: list[StyledChar], edit: dict, fallback_rpr: ET.Element | None
) -> tuple[list[StyledChar], int]:
    old = edit.get("old")
    new = edit.get("new")
    if not isinstance(old, str) or not old or not isinstance(new, str) or old == new:
        raise ValueError("Each edit needs distinct non-empty old and new strings")
    red_text = edit.get("red_text")
    if red_text is not None and (not isinstance(red_text, str) or not red_text):
        raise ValueError("red_text must be a non-empty string")

    text = "".join(item.text for item in chars)
    spans = selected_spans(text, edit)
    for start, end in reversed(spans):
        replacement = replacement_chars(chars[start:end], old, new, red_text, fallback_rpr)
        chars[start:end] = replacement
    return chars, len(spans)


def write_inline_string(cell: ET.Element, chars: list[StyledChar]) -> None:
    for child in list(cell):
        if child.tag in {q(MAIN, "v"), q(MAIN, "is")}:
            cell.remove(child)
    cell.set("t", "inlineStr")
    inline = ET.Element(q(MAIN, "is"))

    groups: list[tuple[str, ET.Element | None]] = []
    for item in chars:
        if groups and style_key(groups[-1][1]) == style_key(item.rpr):
            groups[-1] = (groups[-1][0] + item.text, groups[-1][1])
        else:
            groups.append((item.text, clone(item.rpr)))

    for text, rpr in groups:
        run = ET.SubElement(inline, q(MAIN, "r"))
        if rpr is not None:
            run.append(rpr)
        text_node = ET.SubElement(run, q(MAIN, "t"))
        text_node.set(q(XML_NS, "space"), "preserve")
        text_node.text = text
    cell.append(inline)


def workbook_parts(files: dict[str, bytes]) -> tuple[dict[str, str], list[ET.Element]]:
    workbook = parse_xml(files["xl/workbook.xml"])
    relationships = parse_xml(files["xl/_rels/workbook.xml.rels"])
    rel_targets = {
        rel.get("Id"): rel.get("Target")
        for rel in relationships.findall(q(REL_PKG, "Relationship"))
    }
    sheets: dict[str, str] = {}
    for sheet in workbook.findall(f"{q(MAIN, 'sheets')}/{q(MAIN, 'sheet')}"):
        rel_id = sheet.get(q(REL_DOC, "id"))
        target = rel_targets.get(rel_id)
        if target is None:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = posixpath.normpath(posixpath.join("xl", target))
        sheets[sheet.get("name", "")] = path

    shared: list[ET.Element] = []
    if "xl/sharedStrings.xml" in files:
        shared_root = parse_xml(files["xl/sharedStrings.xml"])
        shared = shared_root.findall(q(MAIN, "si"))
    return sheets, shared


def copy_zip_info(info):
    result = copy.copy(info)
    result.compress_type = info.compress_type
    return result


def cell_font_run_properties(cell: ET.Element, styles_root: ET.Element) -> ET.Element | None:
    """Convert the cell style's effective font to rich-text run properties."""
    cell_xfs = styles_root.find(q(MAIN, "cellXfs"))
    fonts = styles_root.find(q(MAIN, "fonts"))
    if cell_xfs is None or fonts is None:
        return None
    style_index = int(cell.get("s", "0"))
    xfs = cell_xfs.findall(q(MAIN, "xf"))
    if style_index >= len(xfs):
        raise ValueError(f"Invalid cell style index: {style_index}")
    font_index = int(xfs[style_index].get("fontId", "0"))
    font_items = fonts.findall(q(MAIN, "font"))
    if font_index >= len(font_items):
        raise ValueError(f"Invalid font index: {font_index}")

    result = ET.Element(q(MAIN, "rPr"))
    for child in font_items[font_index]:
        copied = clone(child)
        if copied is None:
            continue
        if copied.tag == q(MAIN, "name"):
            copied.tag = q(MAIN, "rFont")
        result.append(copied)
    return result if len(result) else None


def patch_workbook(input_path: Path, output_path: Path, edits_path: Path, overwrite: bool) -> dict:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output must be different; formal sources must never be edited in place")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")

    payload = json.loads(edits_path.read_text(encoding="utf-8-sig"))
    edits = payload.get("edits") if isinstance(payload, dict) else None
    if not isinstance(edits, list) or not edits:
        raise ValueError("Edit JSON must contain a non-empty edits array")

    with ZipFile(input_path, "r") as archive:
        infos = archive.infolist()
        files = {info.filename: archive.read(info.filename) for info in infos}

    sheet_paths, shared_strings = workbook_parts(files)
    styles_root = parse_xml(files["xl/styles.xml"])
    grouped: dict[tuple[str, str], list[dict]] = {}
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("Every edit entry must be an object")
        sheet_name = edit.get("sheet")
        cell_address = edit.get("cell")
        if sheet_name not in sheet_paths:
            raise ValueError(f"Unknown sheet: {sheet_name!r}")
        if not isinstance(cell_address, str) or not re.fullmatch(r"[A-Za-z]{1,3}[1-9]\d*", cell_address):
            raise ValueError(f"Invalid cell address: {cell_address!r}")
        grouped.setdefault((sheet_name, cell_address.upper()), []).append(edit)

    modified_parts: set[str] = set()
    report: list[dict] = []
    sheet_roots: dict[str, ET.Element] = {}
    for (sheet_name, cell_address), cell_edits in grouped.items():
        part = sheet_paths[sheet_name]
        root = sheet_roots.setdefault(part, parse_xml(files[part]))
        cell = root.find(f".//{q(MAIN, 'c')}[@r='{cell_address}']")
        if cell is None:
            raise ValueError(f"Cell not found: {sheet_name}!{cell_address}")
        if cell.find(q(MAIN, "f")) is not None:
            raise ValueError(f"Formula cell must be updated through its source: {sheet_name}!{cell_address}")

        fallback_rpr = cell_font_run_properties(cell, styles_root)
        chars = cell_chars(cell, shared_strings, fallback_rpr)
        before = "".join(item.text for item in chars)
        replacements = 0
        for edit in cell_edits:
            chars, count = apply_edit(chars, edit, fallback_rpr)
            replacements += count
        after = "".join(item.text for item in chars)
        write_inline_string(cell, chars)
        modified_parts.add(part)
        report.append({
            "sheet": sheet_name,
            "cell": cell_address,
            "replacements": replacements,
            "before": before,
            "after": after,
        })

    for part in modified_parts:
        files[part] = serialize_xml(sheet_roots[part])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=output_path.stem + "-", suffix=output_path.suffix, dir=output_path.parent)
    os.close(handle)
    temporary_path = Path(temporary_name)
    try:
        with ZipFile(temporary_path, "w") as archive:
            for info in infos:
                archive.writestr(copy_zip_info(info), files[info.filename])
        with ZipFile(temporary_path, "r") as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f"Invalid ZIP member after patch: {bad_member}")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "output": str(output_path),
        "modified_parts": sorted(modified_parts),
        "changed_cells": len(report),
        "edits": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Read-only source workbook")
    parser.add_argument("--output", required=True, type=Path, help="Destination working copy")
    parser.add_argument("--edits", required=True, type=Path, help="UTF-8 JSON edit specification")
    parser.add_argument("--overwrite", action="store_true", help="Replace an authorized existing working copy")
    args = parser.parse_args()
    try:
        result = patch_workbook(args.input, args.output, args.edits, args.overwrite)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
