#!/usr/bin/env python3
"""Inventory Salesforce review inputs without extracting or modifying them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


DESIGN_EXTENSIONS = {".xlsx", ".xls", ".docx", ".pdf"}
TEST_SUFFIXES = {"test.cls", "tests.cls"}
METADATA_EXTENSIONS = {
    ".cls", ".trigger", ".flow-meta.xml", ".object-meta.xml",
    ".field-meta.xml", ".permissionset-meta.xml", ".profile-meta.xml",
    ".validationrule-meta.xml", ".sharingrules-meta.xml",
}
IGNORED_DIRS = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv"}


def classify(name: str) -> str:
    lower = name.lower().replace("\\", "/")
    if any(lower.endswith(suffix) for suffix in TEST_SUFFIXES):
        return "テスト"
    if any(lower.endswith(ext) for ext in METADATA_EXTENSIONS):
        return "実装"
    if Path(lower).suffix in DESIGN_EXTENSIONS:
        return "設計書"
    if lower.endswith(".zip"):
        return "ZIP"
    return "その他"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_file(path: Path, root: Path) -> list[dict[str, object]]:
    stat = path.stat()
    relative = str(path.relative_to(root)) if path != root else path.name
    row: dict[str, object] = {
        "path": relative,
        "kind": classify(path.name),
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "sha256": sha256(path),
    }
    rows = [row]
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    rows.append({
                        "path": f"{relative}!/{item.filename}",
                        "kind": classify(item.filename),
                        "size": item.file_size,
                        "modified": None,
                        "sha256": None,
                    })
        except zipfile.BadZipFile:
            row["error"] = "invalid zip"
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.input.resolve()
    if not target.exists():
        parser.error(f"input does not exist: {target}")

    root = target if target.is_dir() else target.parent
    files = sorted(
        path for path in target.rglob("*")
        if not any(part in IGNORED_DIRS for part in path.relative_to(target).parts)
    ) if target.is_dir() else [target]
    rows: list[dict[str, object]] = []
    for path in files:
        if path.is_file():
            rows.extend(inventory_file(path, root))

    result = {
        "root": str(root),
        "counts": {kind: sum(1 for row in rows if row["kind"] == kind)
                   for kind in sorted({str(row["kind"]) for row in rows})},
        "files": rows,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
