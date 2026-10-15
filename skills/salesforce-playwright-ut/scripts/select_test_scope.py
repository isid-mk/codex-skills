"""Select formula-logic, validation and button-visibility cases offline; reject out-of-scope execution/result IDs."""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys

ALLOWED_CATEGORIES = frozenset(('数式項目', '入力規則', 'ボタン', '画面イメージ', 'ページレイアウト'))

def in_scope(row):
    category = row.get('category')
    if category in ('数式項目', '入力規則'):
        return True
    if category not in ('ボタン', '画面イメージ', 'ページレイアウト'):
        return False
    if row.get('testKind') == 'button-visibility':
        return True
    text = '\n'.join(str(row.get(k) or '') for k in ('viewpoint', 'steps', 'expected'))
    return category == 'ボタン' and bool(re.search(r'表示有無|表示条件|非表示|ボタン(?:の)?表示', text))

def read_json(filename):
    source = pathlib.Path(filename).resolve()
    versions = source.parent / '.file-versions' / source.name
    candidates = sorted(p for p in versions.glob('*.json') if re.fullmatch(r'\d{15}-\d{6}-[a-f0-9-]+\.json', p.name))
    physical = candidates[-1] if candidates else source
    return json.loads(physical.read_text(encoding='utf-8-sig')), physical

def case_id(row):
    if not isinstance(row, dict):
        raise ValueError('case/result is not an object')
    identifier = row.get('caseId') or (row.get('target') or {}).get('caseId') or row.get('id')
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError('case/result identifier missing')
    return identifier

def select(catalog, requested=None, source=None):
    if not isinstance(catalog, dict) or not isinstance(catalog.get('cases'), list):
        raise ValueError('catalog.cases missing')
    cases = catalog['cases']
    identifiers = [case_id(c) for c in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('duplicate catalog case identifiers')
    if source and source not in {c.get('sourceId') for c in cases}:
        raise ValueError('unknown source: ' + source)
    eligible = [c for c in cases if (not source or c.get('sourceId') == source) and in_scope(c)]
    allowed = {case_id(c) for c in eligible}
    if requested is not None:
        if len(requested) != len(set(requested)) or not requested or any(not c for c in requested):
            raise ValueError('empty or duplicate requested identifiers')
        outside = sorted(set(requested) - allowed)
        if outside:
            raise ValueError('対象外または不明なケース: ' + ', '.join(outside))
        eligible = [c for c in eligible if case_id(c) in set(requested)]
    if not eligible:
        raise ValueError('対象ケース0件: browser/data preparation must not start')
    return eligible

def validate_rows(value, allowed, label):
    if isinstance(value, dict):
        value = value.get('results', value.get('cases'))
    if not isinstance(value, list):
        raise ValueError(label + ' must be an array or contain results/cases')
    outside = sorted({case_id(r) for r in value} - allowed)
    if outside:
        raise ValueError(label + ' contains excluded/unknown cases: ' + ', '.join(outside))
    for row in value:
        if 'category' in row and row['category'] not in ALLOWED_CATEGORIES:
            raise ValueError(label + ' category mismatch: ' + case_id(row))
    return len(value)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--source')
    parser.add_argument('--cases', help='Comma-separated IDs; omission selects all in-scope cases')
    parser.add_argument('--plan', help='Execution/preparation case plan to validate before browser access')
    parser.add_argument('--results', help='Live results/state to validate before reporting')
    parser.add_argument('--out', help='Create a new scope manifest; never overwrite')
    args = parser.parse_args(argv)
    try:
        catalog, physical = read_json(args.catalog)
        selected = select(catalog, args.cases.split(',') if args.cases is not None else None, args.source)
        allowed = {case_id(c) for c in selected}
        checked = {}
        for kind in ('plan', 'results'):
            if getattr(args, kind):
                value, actual = read_json(getattr(args, kind))
                checked[kind] = {'rows': validate_rows(value, allowed, kind), 'physicalSource': str(actual)}
        manifest = {
            'scope': 'formula-logic-validation-button-visibility',
            'sourceFingerprint': catalog.get('fingerprint'),
            'catalogSource': str(physical),
            'catalogSha256': hashlib.sha256(physical.read_bytes()).hexdigest(),
            'allowedCategories': sorted(ALLOWED_CATEGORIES),
            'selectedCount': len(selected),
            'countsByCategory': dict(collections.Counter(c['category'] for c in selected)),
            'caseIds': [case_id(c) for c in selected],
            'cases': selected,
            'excluded': [{'id': case_id(c), 'category': c.get('category'), 'reason': 'このスキルの対象外または今回の指定外'} for c in catalog['cases'] if case_id(c) not in allowed],
            'checked': checked,
            'networkAccess': False,
            'SalesforceExecuted': False,
        }
        if args.out:
            destination = pathlib.Path(args.out).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('x', encoding='utf-8') as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'selectedCount': len(selected), 'countsByCategory': manifest['countsByCategory'], 'excludedCount': len(manifest['excluded']), 'checks': checked, 'caseIds': manifest['caseIds']}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'scopeReady': False, 'error': str(error), 'networkAccess': False}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
