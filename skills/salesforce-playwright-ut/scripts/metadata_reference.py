"""Resolve the metadata ZIP from the reference workbook without copying it."""
import argparse
import json
from pathlib import Path
import openpyxl

INDEX_NAME = 'テスト参照資料一覧.xlsx'


def resolve_metadata(workspace):
    index = Path(workspace).resolve() / INDEX_NAME
    candidates = []
    book = openpyxl.load_workbook(index, read_only=True, data_only=True)
    try:
        for sheet in book:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, ())
            if not all(name in header for name in ('種別', '資料名', '格納先のパス')):
                continue
            kind, name, location = [header.index(key) for key in ('種別', '資料名', '格納先のパス')]
            for row in rows:
                if str(row[kind] or '').strip() != 'メタデータ':
                    continue
                filename = str(row[name] or '').strip()
                value = str(row[location] or '').strip()
                if not value or not filename.lower().endswith('.zip') or Path(filename).name != filename:
                    raise ValueError('メタデータの資料名と格納先のパスを確認してください')
                target = Path(value)
                if not target.is_absolute():
                    target = index.parent / target
                if target.suffix.lower() == '.zip':
                    if target.name != filename:
                        raise ValueError('メタデータの資料名とZIPパスが不一致です')
                else:
                    target = target / filename
                candidates.append(target.resolve())
    finally:
        book.close()
    if len(candidates) != 1:
        raise ValueError('一覧からメタデータZIPを一意に特定できません')
    if not candidates[0].is_file():
        raise FileNotFoundError('一覧に記載されたメタデータZIPが見つかりません: ' + str(candidates[0]))
    return candidates[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    args = parser.parse_args()
    print(json.dumps({'path': str(resolve_metadata(args.workspace))}, ensure_ascii=False))
