#!/usr/bin/env python3
"""Classify object-label Grep CSV hits and emit JSON for workbook authoring."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


DIRECT_TYPES = {"Cell", "Formula", "DrawingOrTextBox", "SheetName"}
DERIVED_SUFFIXES = (
    "番号", "ID", "ＩＤ", " Id", " ID", "名", "区分", "状態", "収支", "採番",
    "管理", "一覧", "詳細", "登録", "作成", "更新", "確認", "群", "テーブル", "TBL",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"CSV encoding could not be read: {last_error}")


def design_info(file_path: str) -> dict[str, str]:
    parts = file_path.split("\\")
    index = next((i for i, part in enumerate(parts) if re.search(r"JFC_CRM(?:外部|内部)設計書一式", part)), -1)
    base = parts[index] if index >= 0 else ""
    phase = "外部設計" if "外部" in base else "内部設計" if "内部" in base else "その他"
    doc_type = parts[index + 1] if index >= 0 and index + 1 < len(parts) else ""
    return {
        "phase": phase,
        "doc_type": doc_type,
        "file_name": parts[-1] if parts else file_path,
        "relative_path": "\\".join(parts[index + 1 :]) if index >= 0 else file_path,
    }


def mask_protected(text: str, old: str, protect_terms: list[str]) -> tuple[str, dict[str, str]]:
    derived_terms = [old + suffix for suffix in DERIVED_SUFFIXES if (old + suffix) in text]
    terms = sorted(set(derived_terms + protect_terms), key=len, reverse=True)
    masked = text
    mapping: dict[str, str] = {}
    for index, term in enumerate(terms):
        if not term or term not in masked:
            continue
        token = f"__PROTECTED_{index}__"
        masked = masked.replace(term, token)
        mapping[token] = term
    return masked, mapping


def classify(hit: dict, old: str, new: str, protect_terms: list[str]) -> dict[str, str]:
    text = " ／ ".join(hit["matched_texts"])
    sheet = hit.get("sheet_name", "")
    escaped = re.escape(old)

    if re.search(r"版履歴|変更履歴|更新履歴|レビュー履歴|QA", sheet, re.I):
        return {"code": "D", "label": "対象外", "reason": "履歴は当時の名称を保持", "proposal": "変更しない"}
    if hit["object_type"] == "SheetName":
        return {"code": "C", "label": "要確認", "reason": "シート名と参照関係への影響を確認", "proposal": "原則維持。必要時のみ変更"}
    if hit["object_type"] == "Formula":
        return {"code": "B", "label": "参照元対応", "reason": "数式の表示値", "proposal": f"参照元を「{new}」に変更"}

    masked, protected = mask_protected(text, old, protect_terms)
    explicit = re.search(fr"{escaped}.{{0,8}}(?:レコード|オブジェクト)|(?:レコード|オブジェクト).{{0,8}}{escaped}", masked)
    grammar = re.search(fr"{escaped}(?:に|を|へ|から|の|が|と)", masked)
    field_path = re.search(fr"{escaped}[.．]", masked)
    relation = re.search(fr"参照関係\s*[（(]?{escaped}", masked)
    exact = re.fullmatch(fr"\s*{escaped}\s*", masked)
    standalone = re.search(fr"(?:^|[\s、。・:：\[\]◆「」（）()]){escaped}(?:$|[\s、。・:：\[\]◆「」（）()])", masked)

    if explicit or grammar or field_path or relation or exact or standalone:
        proposal = masked.replace(old, new)
        for token, term in protected.items():
            proposal = proposal.replace(token, term)
        reason = "対象オブジェクトをレコード／オブジェクトとして明示" if explicit else "対象オブジェクトの論理名・表示名として使用"
        return {"code": "A", "label": "必須対応", "reason": reason, "proposal": proposal}

    if protected:
        return {"code": "C", "label": "要確認", "reason": "独立した項目・機能・処理名の可能性", "proposal": "実際の表示ラベル変更対象に含む場合のみ変更"}
    return {"code": "C", "label": "要確認", "reason": "対象オブジェクト参照か一般名詞かを確認", "proposal": f"対象オブジェクトを指す場合は「{new}」に変更"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--old-label", required=True)
    parser.add_argument("--new-label", required=True)
    parser.add_argument("--protect-term", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    old = args.old_label.strip()
    new = args.new_label.strip()
    if not old or not new:
        raise SystemExit("Old and new labels must not be blank")

    rows = read_csv(args.input)
    required = {"file_path", "sheet_name", "object_type", "location", "matched_text"}
    missing = sorted(required - set(rows[0].keys() if rows else []))
    if missing:
        raise SystemExit(f"Missing CSV columns: {', '.join(missing)}")

    groups: dict[tuple[str, str, str, str], dict] = {}
    for source_row, row in enumerate(rows, start=2):
        if row.get("object_type", "") not in DIRECT_TYPES:
            continue
        key = (row.get("file_path", ""), row.get("sheet_name", ""), row.get("object_type", ""), row.get("location", ""))
        hit = groups.setdefault(key, {
            "file_path": key[0], "sheet_name": key[1], "object_type": key[2], "location": key[3],
            "matched_texts": [], "source_rows": [],
        })
        if row.get("matched_text", "") not in hit["matched_texts"]:
            hit["matched_texts"].append(row.get("matched_text", ""))
        hit["source_rows"].append(source_row)

    protect_terms = [term.strip() for term in args.protect_term if term.strip()]
    details = [{**hit, **design_info(hit["file_path"]), **classify(hit, old, new, protect_terms)} for hit in groups.values()]
    details.sort(key=lambda d: ({"A": 1, "B": 2, "C": 3, "D": 4}[d["code"]], d["phase"], d["doc_type"], d["file_name"], d["sheet_name"], d["location"]))

    docs: dict[str, dict] = {}
    for detail in details:
        doc = docs.setdefault(detail["file_path"], {
            **design_info(detail["file_path"]), "file_path": detail["file_path"],
            "counts": {"A": 0, "B": 0, "C": 0, "D": 0}, "sheets": set(),
        })
        doc["counts"][detail["code"]] += 1
        if detail["sheet_name"]:
            doc["sheets"].add(detail["sheet_name"])

    document_rows = []
    for doc in docs.values():
        mandatory = doc["counts"]["A"]
        canonical = bool(re.search(r"オブジェクト設計|オブジェクト一覧|ER図|権限設計", doc["doc_type"] + doc["file_name"]))
        priority = "P1" if mandatory >= 10 or canonical else "P2" if mandatory or doc["counts"]["B"] else "P3"
        document_rows.append({**doc, "sheets": sorted(doc["sheets"]), "priority": priority})
    document_rows.sort(key=lambda d: (d["priority"], -d["counts"]["A"], d["phase"], d["doc_type"], d["file_name"]))

    type_counts = Counter(row.get("object_type", "") for row in rows)
    code_counts = Counter(detail["code"] for detail in details)
    payload = {
        "metadata": {
            "input": str(args.input), "old_label": old, "new_label": new,
            "raw_rows": len(rows), "source_files": len({row.get("file_path", "") for row in rows}),
            "direct_rows": sum(1 for row in rows if row.get("object_type", "") in DIRECT_TYPES),
            "unique_direct_locations": len(details),
            "package_internal_rows": sum(1 for row in rows if row.get("object_type", "") not in DIRECT_TYPES),
            "type_counts": dict(type_counts), "classification_counts": dict(code_counts),
            "required_documents": sum(1 for doc in document_rows if doc["counts"]["A"] > 0),
        },
        "documents": document_rows,
        "locations": details,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["metadata"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
