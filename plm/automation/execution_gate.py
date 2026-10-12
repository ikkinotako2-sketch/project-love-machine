"""Credential-free execution preparation gate. CLI is permanently PARKED.

A valid local history is evidence, never authorization to construct a transport.
All approval hashes must be supplied from an independently reviewed commit.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from .ledger import Stop, require

SHA = re.compile(r'[a-f0-9]{40}')
HASH = re.compile(r'[a-f0-9]{64}')
MARKER_KEYS = {'identity', 'operation', 'state', 'prepared_commit_sha', 'approved',
               'plan_sha256', 'source_manifest_sha256', 'workflow_sha256',
               'executor_sha256', 'schema_sha256'}
SAFE = dict.fromkeys(('TEST_ONLY', 'DRY_RUN', 'NO_PUBLISH', 'EMERGENCY_STOP'), True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def path_checked(path):
    require(isinstance(path, str), 'PATH_STOP')
    p = PurePosixPath(path)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == path
            and bool(path) and '\\' not in path and '\x00' not in path, 'PATH_STOP')
    return path


def preparation_paths(values):
    require(isinstance(values, list) and values and len(values) == len(set(values)),
            'PREPARATION_HISTORY_STOP')
    for p in values:
        path_checked(p)
        require(not p.startswith('audit-evidence/'), 'PREPARATION_HISTORY_STOP')
    require(values == sorted(values), 'PREPARATION_HISTORY_STOP')
    return values


def load_pinned_plan(raw, expected_hash):
    require(isinstance(expected_hash, str) and HASH.fullmatch(expected_hash)
            and digest(raw) == expected_hash, 'PLAN_HASH_STOP')
    try:
        plan = json.loads(raw)
        require(plan['version'] == 1 and plan['repository'] ==
                'ikkinotako2-sketch/project-love-machine', 'PLAN_CONTRACT_STOP')
        require(plan['launchable'] is False and plan['execution_approved'] is False
                and plan['safe_flags'] == SAFE, 'PARKED_CONTRACT_STOP')
        require(SHA.fullmatch(plan['preparation_parent']) and
                type(plan['preparation_commit_count']) is int and
                plan['preparation_commit_count'] == 1, 'PREPARATION_HISTORY_STOP')
        preparation_paths(plan['preparation_files'])
        require(len(plan['operations']) > 0, 'OPERATION_CONTRACT_STOP')
        identities = []
        for name, op in plan['operations'].items():
            identity = op['identity']; identities.append(identity)
            require(re.fullmatch(r'provider-neutral-[a-z0-9-]{1,100}', identity),
                    'IDENTITY_STOP')
            require(identity not in {plan['protected_unconsumed_identity'], 'provider-neutral-youtube-oauth-verify-20261012-r1', 'provider-neutral-youtube-oauth-verify-20261012-r2', 'provider-neutral-youtube-oauth-scope-diagnostic-20261012-r1'}, 'IDENTITY_STOP')
            require(op['launchable'] is False and op['execution_approved'] is False
                    and op['marker_state'] == 'NOT_CREATED_NOT_CONSUMED', 'PARKED_CONTRACT_STOP')
            require(all(type(op[k]) is int and op[k] == 0 for k in
                        ('retry', 'rerun', 'resume', 'redirect', 'fallback')), 'RETRY_STOP')
            require(op['marker_path'] == 'audit-evidence/consumed/' + identity + '.json',
                    'MARKER_PATH_STOP')
            require(all(type(v) is int and v >= 0 for v in op['budget'].values()), 'BUDGET_STOP')
            require(name not in op['requires'] and all(d in plan['operations']
                    for d in op['requires']), 'DEPENDENCY_STOP')
        require(len(set(identities)) == len(identities), 'IDENTITY_STOP')
        # Reject dependency cycles; no operation may depend on its own success.
        def walk(name, trail):
            require(name not in trail, 'DEPENDENCY_STOP')
            for dep in plan['operations'][name]['requires']:
                walk(dep, trail + [name])
        for name in plan['operations']:
            walk(name, [])
    except (KeyError, TypeError, ValueError):
        raise Stop('PLAN_SHAPE_STOP') from None
    return plan


class GitAudit:
    """Actual local Git reads only. No fetching, credential reads or mutations."""
    def __init__(self, root):
        self.root = Path(root)

    def git(self, *args):
        try:
            p = subprocess.run(['git', '-C', str(self.root), *args], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=10)
            require(len(p.stdout) <= 1_048_576, 'GIT_OUTPUT_BOUND_STOP')
            return p.stdout
        except (subprocess.SubprocessError, OSError):
            raise Stop('LOCAL_HISTORY_UNKNOWN_STOP') from None

    def raw(self, ref, path):
        require(SHA.fullmatch(ref), 'COMMIT_STOP'); path_checked(path)
        return self.git('show', ref + ':' + path)

    def absent(self, ref, path):
        # ls-tree never conflates a missing commit with a missing path.
        require(SHA.fullmatch(ref), 'COMMIT_STOP'); path_checked(path)
        self.git('cat-file', '-e', ref + '^{commit}')
        return self.git('ls-tree', ref, '--', path) == b''

    def preparation(self, plan, prepared):
        require(SHA.fullmatch(prepared), 'COMMIT_STOP')
        require(self.git('rev-parse', '--is-shallow-repository').strip() == b'false',
                'FULL_HISTORY_REQUIRED')
        root = plan['preparation_parent']
        require(self.git('merge-base', root, prepared).decode().strip() == root,
                'PREPARATION_HISTORY_STOP')
        require(self.git('rev-list', '--count', root + '..' + prepared).strip() == b'1',
                'PREPARATION_HISTORY_STOP')
        require(self.git('show', '-s', '--format=%P', prepared).decode().strip() == root,
                'PREPARATION_HISTORY_STOP')
        actual = self.git('diff', '--name-only', root + '..' + prepared).decode().splitlines()
        require(sorted(actual) == preparation_paths(plan['preparation_files']),
                'PREPARATION_HISTORY_STOP')
        for op in plan['operations'].values():
            for ref in (root, prepared):
                require(self.absent(ref, op['marker_path']), 'ALREADY_CONSUMED_STOP')
        protected = 'audit-evidence/consumed/' + plan['protected_unconsumed_identity'] + '.json'
        require(self.absent(prepared, protected), 'PROTECTED_IDENTITY_STOP')
        return {'full_history': True, 'merge_base': root, 'rev_list': 1,
                'preparation_files_exact': True}

    def marker_history(self, plan, prepared, head, operation, marker_expected_sha):
        facts = self.preparation(plan, prepared)
        require(SHA.fullmatch(head), 'COMMIT_STOP')
        op = plan['operations'][operation]; path = op['marker_path']
        require(self.git('rev-parse', 'HEAD').decode().strip() == head and
                self.git('status', '--porcelain') == b'', 'WORKTREE_STOP')
        require(self.git('show', '-s', '--format=%P', head).decode().strip() == prepared,
                'MARKER_ONLY_HISTORY_STOP')
        require(self.git('show', '-s', '--format=%s', head).decode().strip() ==
                'PLM execution package once ' + op['identity'], 'MARKER_MESSAGE_STOP')
        require(self.git('diff', '--name-status', prepared + '..' + head).decode().splitlines()
                == ['A\t' + path], 'MARKER_ONLY_HISTORY_STOP')
        raw = self.raw(head, path)
        require(HASH.fullmatch(marker_expected_sha) and digest(raw) == marker_expected_sha,
                'MARKER_HASH_STOP')
        marker = json.loads(raw)
        require(set(marker) == MARKER_KEYS and marker['identity'] == op['identity']
                and marker['operation'] == operation and marker['state'] == 'CONSUMED_BEFORE_REMOTE'
                and marker['approved'] is True and marker['prepared_commit_sha'] == prepared,
                'MARKER_CONTRACT_STOP')
        pin_paths = {'plan_sha256': 'readiness/execution-package-plan.json',
                     'source_manifest_sha256': plan['source_manifest'],
                     'workflow_sha256': plan['workflow_path'],
                     'executor_sha256': plan['executor_path'], 'schema_sha256': plan['schema_path']}
        for key, pinned_path in pin_paths.items():
            require(marker[key] == digest(self.raw(prepared, pinned_path)), 'MARKER_PIN_STOP')
        manifest = json.loads(self.raw(prepared, plan['source_manifest']))
        for source, expected in manifest['source_sha256'].items():
            require(digest(self.raw(prepared, source)) == expected, 'SOURCE_DRIFT_STOP')
        facts['marker_exact'] = True
        return facts


def local_event_gate(event, plan):
    require(event.get('repository') == plan['repository'] and
            event.get('branch') == plan['branch'] and event.get('event') == 'push' and
            type(event.get('attempt')) is int and event['attempt'] == 1,
            'EXECUTION_CONTEXT_STOP')


def credential_boundary(*args, **kwargs):
    # Even valid offline marker fixtures never mint authority or release Secrets.
    raise Stop('PARKED_LIVE_EXECUTOR_APPROVAL_REQUIRED')


def main():
    print(json.dumps({'status': 'PARKED_LIVE_EXECUTOR_APPROVAL_REQUIRED',
                      'credentials_read': 0, 'requests': 0, 'state_writes': 0,
                      'execution_markers_created': 0}))



def historical_gate(raw_document, expected_hash, marker_bytes):
    require(digest(raw_document) == expected_hash, 'HISTORY_PIN_STOP')
    doc = json.loads(raw_document)
    require(set(marker_bytes) == {x['identity'] for x in doc['consumed']},
            'HISTORY_EVIDENCE_STOP')
    for item in doc['consumed']:
        require(digest(marker_bytes[item['identity']]) == item['raw_sha256'],
                'HISTORICAL_MARKER_DRIFT_STOP')
    return True


def validate_receipt(receipt, expected):
    """Approval packages never promote a returned ACK into completed work."""
    require(isinstance(receipt, dict) and receipt.get('verified') is True and
            receipt.get('proof_basis') == 'INDEPENDENT_GITHUB_API' and
            receipt.get('phase') == 'completed' and receipt.get('run_attempt') == 1 and
            type(receipt.get('run_attempt')) is int and
            all(receipt.get(k) == expected[k] for k in
                ('job_id', 'identity', 'run_id', 'commit', 'media_sha256')),
            'PREREQUISITE_NOT_INDEPENDENT_COMPLETION_STOP')
    return True


if __name__ == '__main__':
    main()
