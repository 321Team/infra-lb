#!/usr/bin/env python3
"""Read-only evidence supplement. Run as the original operator, without sudo."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile

CLIENTS = {
    'ansible01': ('ansible', 'server01_ansible',
                  'SHA256:IMzyrRaluEPISRA8a6++E2ljufMna9QL3/kLUJIrPSo'),
    'cicd-runner01': ('runner', 'server01_cicd-runner',
                      'SHA256:iJ7UOsZJHE8U/HDICq2/Mai7Wsqn3dTjgR9NQFPSacw'),
}


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def key_state(path):
    try:
        path.lstat()
        return 'PRESENT'
    except FileNotFoundError:
        return 'ABSENT'
    except OSError:
        return 'NOT_VERIFIED_ACCESS_ERROR'


def collect(host, username, home):
    lines = ['test=P1-LB-01 Stage A evidence supplement',
             'timestamp=' + dt.datetime.now(dt.timezone.utc).isoformat(),
             'source_host=' + host, 'source_user=' + username,
             'collection=READ_ONLY', 'handoff_acceptance=PENDING']
    if host == 'k8s-api-lb01':
        for args in (['getenforce'], ['sestatus'], ['getsebool', 'haproxy_connect_any']):
            rc, out, err = command(args)
            lines += ['command=' + ' '.join(args), 'exit_code=' + str(rc), out]
            if err:
                lines.append('stderr=' + err)
        return '20_selinux_state_k8s-api-lb01.txt', lines
    if host not in CLIENTS:
        raise ValueError('Host must be k8s-api-lb01, ansible01, or cicd-runner01')
    role, expected_user, fingerprint = CLIENTS[host]
    if username != expected_user:
        raise ValueError('Run under the original account: ' + expected_user)
    ssh_dir = home / '.ssh'
    if not ssh_dir.is_dir() or not os.access(ssh_dir, os.R_OK | os.X_OK):
        raise ValueError('Original account .ssh directory is not accessible')
    key = ssh_dir / ('p1-lb-01-stage-a-' + role + '-ed25519')
    lines += ['role=' + role, 'expected_key_fingerprint=' + fingerprint,
              'private_key_path=' + str(key),
              'private_key_state=' + key_state(key),
              'public_key_state=' + key_state(Path(str(key) + '.pub')),
              'scope=approved temporary key paths only; other copies are not surveyed']
    log = home / '.local/state/p1-lb-01-stage-a-transfer' / ('revoke_local_' + role + '.txt')
    lines.append('historical_revocation_log=' + str(log))
    try:
        # Read only allowlisted metadata; never read a private/public key file.
        if log.is_symlink():
            raise ValueError('Revocation log symlink needs review')
        content = log.read_text(encoding='utf-8')
        keys = {'test', 'timestamp', 'role', 'source_host', 'key_tag',
                'key_fingerprint', 'server_revocation_prerequisite', 'verdict'}
        fields = {}
        for line in content.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                if k in keys:
                    fields[k] = v
                    lines.append('history.' + k + '=' + v)
        lines += ['historical_log=PRESENT',
                  'historical_fingerprint_match=' + str(fields.get('key_fingerprint') == fingerprint)]
    except FileNotFoundError:
        lines.append('historical_log=MISSING; current absence does not establish deletion date')
    except OSError:
        lines.append('historical_log=NOT_VERIFIED_ACCESS_ERROR')
    lines.append('verdict=REVIEW_REQUIRED; no deletion or approval performed')
    return ('21a_key_revocation_ansible.txt' if role == 'ansible'
            else '21b_key_revocation_runner.txt'), lines


def main():
    if os.getuid() == 0:
        print('[FAIL] Run without sudo as the original operator.', file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        rc, host, err = command(['hostnamectl', '--static'])
        if rc:
            raise ValueError('Hostname check failed: ' + err)
        user = pwd.getpwuid(os.getuid())
        name, lines = collect(host, user.pw_name, Path(user.pw_dir))
        output = Path(tempfile.mkdtemp(prefix='P1-LB-01_Stage_A_Supplement_', dir=Path.cwd()))
        evidence = output / name
        evidence.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        checksum = hashlib.sha256(evidence.read_bytes()).hexdigest()
        sidecar = evidence.with_name(name + '.sha256')
        sidecar.write_text(checksum + '  ' + name + '\n', encoding='utf-8')
        print(evidence.read_text(), end='')
        print('EVIDENCE=' + str(evidence))
        print('SIDECAR=' + str(sidecar))
        return 0
    except (OSError, ValueError) as exc:
        print('[FAIL] ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
