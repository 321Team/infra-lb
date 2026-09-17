#!/usr/bin/env python3
"""Export existing Stage A evidence for review; never create approval evidence."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

REQUIRED = (
    '01_hostnamectl.txt', '02_ip_address.txt', '03_ip_route.txt',
    '04_nmcli_connection.txt', '05_haproxy_version.txt',
    '06_haproxy_config_check.txt', '07_haproxy.cfg',
    '08_haproxy_status.txt', '09_listener.txt', '10_firewalld.txt',
    '11_selinux_boolean.txt', '12_selinux_avc.txt',
    '13_haproxy_stats.csv', '14_haproxy_journal.txt',
    '15_backend_prebootstrap_test.txt', '16_positive_test_nodes.txt',
    '17_positive_test_runner.txt', '18_negative_test.txt',
    '18a_secure_evidence_transfer_control.txt',
    '18b_secure_transfer_ansible_client.txt',
    '18c_secure_transfer_runner_client.txt',
)
REVIEW = '19_stage_a_handoff_review.md'
MANIFEST = '99_SHA256SUMS.txt'
REFERENCE = {
    '16_positive_test_nodes.txt': '3386bfd4cf821c16aa3b522cfa11dafcca72e3c63124b1c1d19b65761eedfcc2',
    '17_positive_test_runner.txt': '1e6b8d5f9f44deb8be37cf9b6bbdb8d93942a454a714b23196118825827cdb54',
    '18_negative_test.txt': '4cf3d23fe3d2b019aedb15604667c226f706b48d3879e2ccff3dc2182e50361c',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_original(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise ValueError(f'MISSING: {path.name}') from None
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size == 0:
            raise ValueError(f'NOT_REGULAR_OR_EMPTY: {path.name}')
        if stat.S_IMODE(before.st_mode) != 0o640:
            raise ValueError(f'MODE_REVIEW_REQUIRED: {path.name}; expected 0640')
        data = stream.read()
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError(f'CHANGED_DURING_READ: {path.name}')
    return data, before


def inspect_manifest(data, hashes):
    if data is None:
        return {'status': 'MISSING_NOT_VERIFIED', 'entries': {}}
    entries = {}
    for line in data.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](?:\./)?([^/\\]+)', line)
        if not match or match.group(2) in ('.', '..'):
            raise ValueError('MANIFEST_FORMAT_REVIEW_REQUIRED')
        name = match.group(2)
        if name in entries:
            raise ValueError(f'DUPLICATE_MANIFEST_ENTRY: {name}')
        entries[name] = match.group(1).lower()
    results = {}
    for name, expected in entries.items():
        if name not in hashes:
            results[name] = 'MISSING_REVIEW_RECORD' if name == REVIEW else 'NOT_EXPORTED_NOT_VERIFIED'
        elif hashes[name] != expected:
            raise ValueError(f'EXISTING_MANIFEST_HASH_MISMATCH: {name}')
        else:
            results[name] = 'MATCH'
    for name in hashes:
        if name != MANIFEST and name not in entries:
            results[name] = 'NOT_LISTED_NOT_VERIFIED'
    complete = bool(results) and all(v == 'MATCH' for v in results.values())
    return {'status': 'ALL_EXPORTED_ORIGINALS_MATCH' if complete else 'PARTIAL_NOT_FULLY_VERIFIED',
            'entries': results}


def export_review(root, output_parent):
    root = root.absolute()
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError('SOURCE_PATH_REVIEW_REQUIRED: symlink or non-directory')
    parent = output_parent.resolve(strict=True)
    if parent == root or root in parent.parents:
        raise ValueError('OUTPUT_MUST_BE_OUTSIDE_EVIDENCE_DIRECTORY')
    originals = {name: read_original(root / name) for name in REQUIRED}
    for name in (REVIEW, MANIFEST):
        if os.path.lexists(root / name):
            originals[name] = read_original(root / name)
    hashes = {name: digest(item[0]) for name, item in originals.items()}
    old_manifest = inspect_manifest(originals.get(MANIFEST, (None,))[0], hashes)
    report = {
        'format_version': '1.1',
        'purpose': 'REVIEW_INPUT_ONLY',
        'export_timestamp_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'source': str(root),
        'required_technical_files': len(REQUIRED),
        'review_record': 'PRESENT_CONTENT_REVIEW_PENDING' if REVIEW in originals else 'MISSING_PENDING',
        'existing_manifest': old_manifest,
        'reference_hash_comparison': {
            name: 'MATCH' if hashes[name] == expected else 'DIFFERENT_REVIEW_REQUIRED'
            for name, expected in REFERENCE.items()
        },
        'files': {name: {'sha256': hashes[name], 'size': len(item[0]),
                         'source_mode': oct(stat.S_IMODE(item[1].st_mode)),
                         'source_mtime_ns': item[1].st_mtime_ns}
                  for name, item in originals.items()},
        'handoff_acceptance': 'PENDING',
        'technical_verdict': 'NOT_REASSESSED',
        'bootstrap_release': 'NOT_AUTHORIZED_BY_THIS_EXPORT',
        'note': 'PACKAGE_SHA256SUMS proves current transfer integrity only; it does not replace 99_SHA256SUMS.txt.',
    }
    # Check source bytes again before producing a review packet.
    for name in originals:
        if digest(read_original(root / name)[0]) != hashes[name]:
            raise ValueError(f'SOURCE_CHANGED: {name}')
    output = Path(tempfile.mkdtemp(prefix='P1-LB-01_Stage_A_Review_', dir=parent))
    package = output / 'review-package'
    stage = package / 'stage-a'
    stage.mkdir(parents=True, mode=0o700)
    for name, (data, metadata) in originals.items():
        target = stage / name
        target.write_bytes(data)
        target.chmod(stat.S_IMODE(metadata.st_mode))
        os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    (package / 'REVIEW_EXPORT_STATUS.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    members = sorted(p for p in package.rglob('*') if p.is_file())
    package_hashes = {str(p.relative_to(package)): digest(p.read_bytes()) for p in members}
    (package / 'PACKAGE_SHA256SUMS').write_text(
        ''.join(f'{h}  {name}\n' for name, h in package_hashes.items()), encoding='utf-8')
    archive = output / 'P1-LB-01_Stage_A_Review_Input_v1.1.tar.gz'
    with tarfile.open(archive, 'w:gz', dereference=False) as tar:
        tar.add(package, arcname=package.name)
    # Verify archived payloads, including the new transfer manifest.
    package_hashes['PACKAGE_SHA256SUMS'] = digest((package / 'PACKAGE_SHA256SUMS').read_bytes())
    with tarfile.open(archive, 'r:gz') as tar:
        for name, expected in package_hashes.items():
            with tar.extractfile(f'review-package/{name}') as member:
                if digest(member.read()) != expected:
                    raise ValueError(f'ARCHIVE_HASH_MISMATCH: {name}')
    sidecar = archive.with_name(archive.name + '.sha256')
    sidecar.write_text(f'{digest(archive.read_bytes())}  {archive.name}\n', encoding='utf-8')
    return archive, sidecar, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('/var/log/fds-evidence/P1-LB-01/stage-a'))
    parser.add_argument('--output-dir', type=Path, default=Path.cwd())
    args = parser.parse_args()
    os.umask(0o077)
    try:
        host = subprocess.check_output(['hostnamectl', '--static'], text=True).strip()
        if host != 'k8s-api-lb01':
            raise ValueError(f'WRONG_HOST: expected k8s-api-lb01; actual {host}')
        archive, sidecar, report = export_review(args.source, args.output_dir)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(f'[FAIL] {exc}', file=sys.stderr)
        return 1
    print('[REVIEW EXPORT READY]')
    print(f'ARCHIVE={archive}')
    print(f'SIDECAR={sidecar}')
    print(f'REVIEW_RECORD={report["review_record"]}')
    print(f'EXISTING_MANIFEST={report["existing_manifest"]["status"]}')
    print('HANDOFF=PENDING; BOOTSTRAP=HOLD; source files unchanged')
    return 0


if __name__ == '__main__':
    sys.exit(main())
