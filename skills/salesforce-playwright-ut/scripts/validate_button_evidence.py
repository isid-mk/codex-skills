"""Check every planned button/profile/condition has a measured result and screenshots."""
import argparse
import json
from pathlib import Path
import sys

KEYS = ('caseId', 'buttonKey', 'profile', 'conditionKey')


def indexed(rows, label):
    if not isinstance(rows, list):
        raise ValueError(label + ' must be an array')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(label + ': row must be an object')
        key = tuple(row.get(k) for k in KEYS)
        if any(not isinstance(k, str) or not k.strip() for k in key):
            raise ValueError(label + ': missing identity key')
        if key in result:
            raise ValueError(label + ': duplicate ' + repr(key))
        if type(row.get('expectedVisible')) is not bool:
            raise ValueError(label + ': expectedVisible must be boolean')
        result[key] = row
    return result


def validate(plan, results, image_base):
    planned = indexed(plan, 'plan')
    measured = indexed(results, 'results')
    if not planned:
        raise ValueError('empty plan')
    extra = set(measured) - set(planned)
    if extra:
        raise ValueError('unplanned results: ' + repr(sorted(extra)))
    issues, counts = [], {'OK': 0, 'NG': 0, '保留': 0, 'missing': 0}
    for key, target in planned.items():
        row = measured.get(key)
        if row is None:
            counts['missing'] += 1
            issues.append({'key': key, 'reason': 'result missing'})
            continue
        status = row.get('status')
        if status not in ('OK', 'NG', '保留'):
            raise ValueError('unknown status: ' + repr(key))
        counts[status] += 1
        errors = []
        if row['expectedVisible'] != target['expectedVisible']:
            errors.append('expected value changed')
        if status == '保留':
            if not row.get('reason'):
                errors.append('pending reason missing')
        else:
            if type(row.get('actualVisible')) is not bool:
                errors.append('actualVisible not measured')
            elif (row['actualVisible'] == target['expectedVisible']) != (status == 'OK'):
                errors.append('status contradicts observed visibility')
            if row.get('identityVerified') is not True or row.get('pageReady') is not True:
                errors.append('identity/page not verified')
            if not row.get('userId') or not row.get('capturedAt'):
                errors.append('user/time missing')
            images = row.get('screenshots')
            if not isinstance(images, list) or not images:
                errors.append('screenshots missing')
            else:
                for image in images:
                    if not isinstance(image, str) or not image:
                        errors.append('invalid screenshot path')
                        continue
                    p = Path(image)
                    if not p.is_absolute():
                        p = image_base / p
                    if p.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp') or not p.is_file() or p.stat().st_size == 0:
                        errors.append('screenshot unavailable: ' + image)
        if errors:
            issues.append({'key': key, 'reason': '; '.join(errors)})
    # Same source image may cover several buttons for one profile, never different profiles.
    owners = {}
    for key, row in measured.items():
        for image in row.get('screenshots') or []:
            if not isinstance(image, str):
                continue
            path = Path(image)
            path = (path if path.is_absolute() else image_base / path).resolve()
            previous = owners.setdefault(path, key[2])
            if previous != key[2]:
                issues.append({'key': key, 'reason': 'image reused across profiles: ' + str(path)})
    complete = not issues and not counts['保留'] and not counts['missing']
    overall = 'NG' if counts['NG'] else ('OK' if complete else '保留')
    return {'plannedCount': len(planned), 'counts': counts, 'issues': issues,
            'coverageComplete': complete, 'overall': overall, 'SalesforceExecutedByValidator': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--results', required=True)
    parser.add_argument('--out', help='Create a new coverage manifest, never overwrite')
    args = parser.parse_args()
    try:
        p = json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
        r = json.loads(Path(args.results).read_text(encoding='utf-8-sig'))
        report = validate(p.get('cases') if isinstance(p, dict) else p,
                          r.get('results') if isinstance(r, dict) else r,
                          Path(args.results).resolve().parent)
        if args.out:
            with Path(args.out).open('x', encoding='utf-8') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['coverageComplete'] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'coverageComplete': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
