"""Read-only preflight for the existing Kokumin CRM project, never Salesforce."""
import argparse
import hashlib
import json
import pathlib
import re
import sys
from urllib.parse import urlparse
from metadata_reference import resolve_metadata


def check(workspace, run_id=None):
    root = pathlib.Path(workspace).resolve()
    issues = []
    notes = []
    required = [
        'automation/config/local.json', 'automation/src/cli.ts',
        'automation/src/browser.ts', 'automation/src/closed-field.ts',
        'automation/src/safety.ts', 'automation/src/display-proof.ts',
        'automation/src/login-as.ts', 'automation/src/evidence-groups.ts',
        'automation/scripts/read_all_rule_formula.py',
        'automation/scripts/report-all-rule-formula.ts',
        'automation/scripts/debug/post-result-health.ts',
        'automation/scripts/debug/reconcile-name-readonly.ts',
        'automation/scripts/verify_pilot_output.py',
        'automation/実行.ps1', 'automation/CDPブラウザー起動.cmd',
        'テスト参照資料一覧.xlsx',
        'Salesforce単体テスト自動化_事前確認事項.xlsx',
    ]
    for name in required:
        if not (root / name).is_file():
            issues.append('missing_file:' + name)
    try:
        config = json.loads((root / 'automation/config/local.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        config = {}
        issues.append('config_unreadable')
    expected = {
        'orgId': '00DBS000007Wzm3', 'channel': 'msedge', 'connectMode': 'cdp',
        'persistentAuthApproved': True, 'metadataAuth': 'export',
        'recordMutationApproved': True, 'notificationsReviewed': True,
        'recordDeletionApproved': False, 'recordEditMode': 'inline-name',
        'saveActivation': 'dom-click',
    }
    for key, value in expected.items():
        if config.get(key) != value:
            issues.append('project_setting_mismatch:' + key)
    origin = urlparse(config.get('sandboxOrigin', ''))
    account = urlparse(config.get('accountRecordUrl', ''))
    if (origin.scheme != 'https' or origin.hostname != 'force-enterprise-4218--dev01.sandbox.lightning.force.com'
            or account.scheme != origin.scheme or account.netloc != origin.netloc
            or account.path != '/lightning/r/Account/001BS00001iwwUqYAI/view'):
        issues.append('wrong_sandbox_or_record')
    metadata = config.get('metadataExport', {})
    metadata_hash = None
    if metadata.get('orgId') != expected['orgId'] or not metadata.get('exportedAt'):
        issues.append('metadata_provenance_missing_or_mismatched')
    try:
        export = resolve_metadata(root)
    except (OSError, ValueError, KeyError) as error:
        issues.append('metadata_reference_unavailable:' + str(error))
    else:
        metadata_hash = hashlib.sha256(export.read_bytes()).hexdigest()
        notes.append('exported_metadata_is_a_snapshot_not_a_live_fetch')
    if run_id:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
            issues.append('invalid_run_id')
        else:
            folder = root / 'automation/runs' / run_id
            try:
                state = json.loads((folder / 'state.json').read_text(encoding='utf-8-sig'))
                if state.get('pending') is not None:
                    issues.append('pending_save:read_only_reconciliation_required')
                catalog = json.loads((folder / 'catalog.json').read_text(encoding='utf-8-sig'))
                inputs = [dict(catalog.get('index', {}))]
                for source in catalog.get('sources', []):
                    inputs.append(dict(source))
                    inputs.extend(source.get('references', []))
                seen = set()
                for item in inputs:
                    key = item.get('path')
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    file = pathlib.Path(key)
                    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != item.get('hash'):
                        issues.append('source_changed:new_run_required:' + item.get('id', file.name))
                notes.append('run_status_is_historical_not_current_browser_identity')
            except (OSError, ValueError, KeyError):
                issues.append('run_state_or_catalog_unreadable')
    notes.append('browser_org_user_network_and_evidence_must_be_verified_separately')
    return {
        'localPrerequisitesReady': not issues,
        'SalesforceReadyOrPassed': False,
        'issues': issues, 'notes': notes,
        'metadataSha256': metadata_hash,
        'metadataExportedAt': metadata.get('exportedAt'),
        'changedFiles': False, 'networkAccess': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--run')
    args = parser.parse_args()
    result = check(args.workspace, args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['localPrerequisitesReady'] else 2


if __name__ == '__main__':
    sys.exit(main())
