#!/usr/bin/python3
"""Root-owned least-privilege helper for P1-LB-01 Stage B.

Installed path: /usr/local/sbin/p1-lb-stageb-privileged
Only the exact Stage B command shapes below are accepted. No shell is used.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

TRUSTED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
EXPECTED_SUDO_USER = "server01_k8s-api-lb"
CONFIG = "/etc/haproxy/haproxy.cfg"
CFGDIR = "/etc/haproxy/conf.d"
SOCKET = "/var/lib/haproxy/stats"
POLICY = "/etc/sudoers.d/p1-lb-stageb"
PREFIX = "p1lb_"
MAX_INPUT_BYTES = 4096
COMMAND_TIMEOUT_SECONDS = 3


class Stop(RuntimeError):
    pass


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def table_name(run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise Stop("INVALID_RUN_ID")
    return PREFIX + run_id


def rules(run_id):
    name = table_name(run_id)
    return ('create table inet ' + name + ' { comment "P1-LB-01:' + run_id + '"; }\n'
            'add set inet ' + name + ' target { type ipv4_addr; flags timeout; timeout 60s; }\n'
            'add element inet ' + name + ' target { 10.1.93.104 timeout 60s }\n'
            'add chain inet ' + name + ' output { type filter hook output priority 0; policy accept; }\n'
            'add rule inet ' + name + ' output oifname "ens160" ip saddr 10.1.93.109 '
            'ip daddr @target tcp dport 6443 counter drop\n').encode("ascii")


def trusted_binary(name):
    value = shutil.which(name, path=TRUSTED_PATH)
    if not value:
        raise Stop("MISSING_TOOL_" + name)
    return str(Path(value).resolve())


def current_haproxy_pid():
    systemctl = trusted_binary("systemctl")
    proc = subprocess.run([systemctl, "show", "haproxy.service", "--property=MainPID", "--value"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={"PATH": TRUSTED_PATH, "LC_ALL": "C", "LANG": "C"},
                          timeout=COMMAND_TIMEOUT_SECONDS, check=False)
    if proc.returncode != 0:
        raise Stop("HAPROXY_PID_QUERY_FAILED")
    value = proc.stdout.decode(errors="replace").strip()
    if not value.isdigit() or int(value) <= 1:
        raise Stop("INVALID_HAPROXY_MAIN_PID")
    return value


def _shape(argv, input_bytes):
    if not argv:
        raise Stop("MISSING_COMMAND")
    name = Path(argv[0]).name

    if name == "cat":
        if len(argv) != 2 or not re.fullmatch(r"/proc/[1-9][0-9]*/cmdline", argv[1]):
            raise Stop("CAT_PATH_NOT_ALLOWED")
        if input_bytes:
            raise Stop("UNEXPECTED_STDIN")
        return

    if name == "find":
        expected = [argv[0], CFGDIR, "-maxdepth", "1", "-name", "*.cfg", "!", "-name", ".*", "-print"]
        if argv != expected or input_bytes:
            raise Stop("FIND_ARGS_NOT_ALLOWED")
        return

    if name == "sha256sum":
        if len(argv) < 3 or argv[1] != "--" or input_bytes:
            raise Stop("SHA256SUM_ARGS_NOT_ALLOWED")
        paths = argv[2:]
        if paths[0] != CONFIG or len(paths) > 101:
            raise Stop("SHA256SUM_PATH_NOT_ALLOWED")
        extra = paths[1:]
        if extra != sorted(extra) or len(extra) != len(set(extra)):
            raise Stop("SHA256SUM_PATH_ORDER_INVALID")
        pattern = re.compile(re.escape(CFGDIR) + r"/[A-Za-z0-9_][A-Za-z0-9_.-]*\.cfg")
        if any(not pattern.fullmatch(p) for p in extra):
            raise Stop("SHA256SUM_PATH_NOT_ALLOWED")
        return

    if name == "socat":
        if (len(argv) != 5 or argv[1:3] not in (["-T", "1"], ["-T", "3"])
                or argv[3] != "-" or argv[4] != "UNIX-CONNECT:" + SOCKET):
            raise Stop("SOCAT_ARGS_NOT_ALLOWED")
        if input_bytes != b"show stat\n":
            raise Stop("SOCAT_INPUT_NOT_ALLOWED")
        return

    if name == "haproxy":
        if argv != [argv[0], "-c", "-f", CONFIG, "-f", CFGDIR] or input_bytes:
            raise Stop("HAPROXY_ARGS_NOT_ALLOWED")
        return

    if name == "nft":
        if argv == [argv[0], "-j", "list", "tables"] and not input_bytes:
            return
        if argv == [argv[0], "-s", "-j", "list", "table", "inet", "firewalld"] and not input_bytes:
            return
        if len(argv) == 6 and argv[1:5] == ["-j", "list", "table", "inet"]:
            name_arg = argv[5]
            if not re.fullmatch(PREFIX + r"[0-9a-f]{32}", name_arg) or input_bytes:
                raise Stop("NFT_TABLE_NOT_ALLOWED")
            return
        if len(argv) == 5 and argv[1:4] == ["delete", "table", "inet"]:
            name_arg = argv[4]
            if not re.fullmatch(PREFIX + r"[0-9a-f]{32}", name_arg) or input_bytes:
                raise Stop("NFT_TABLE_NOT_ALLOWED")
            return
        if argv in ([argv[0], "-c", "-f", "-"], [argv[0], "-f", "-"]):
            if not input_bytes or len(input_bytes) > MAX_INPUT_BYTES:
                raise Stop("NFT_RULE_INPUT_INVALID")
            first = input_bytes.splitlines()[0].decode("ascii", errors="strict")
            match = re.fullmatch(r'create table inet p1lb_([0-9a-f]{32}) \{ comment "P1-LB-01:\1"; \}', first)
            if not match or input_bytes != rules(match.group(1)):
                raise Stop("NFT_RULE_INPUT_NOT_ALLOWED")
            return
        raise Stop("NFT_ARGS_NOT_ALLOWED")

    raise Stop("COMMAND_NOT_ALLOWED_" + name)


def validate_request(argv, input_bytes):
    if not argv:
        raise Stop("MISSING_COMMAND")
    name = Path(argv[0]).name
    expected = trusted_binary(name)
    if Path(argv[0]).resolve() != Path(expected):
        raise Stop("UNTRUSTED_BINARY_PATH")
    _shape(argv, input_bytes)
    if name == "cat" and argv[1] != "/proc/" + current_haproxy_pid() + "/cmdline":
        raise Stop("CAT_PID_NOT_HAPROXY")
    return [expected, *argv[1:]]


def ensure_context(expected_sha=None):
    if os.geteuid() != 0 or os.getuid() != 0:
        raise Stop("HELPER_REQUIRES_ROOT")
    if os.environ.get("SUDO_USER") != EXPECTED_SUDO_USER:
        raise Stop("UNEXPECTED_SUDO_USER")
    path = Path(__file__)
    if path.is_symlink():
        raise Stop("HELPER_SYMLINK_FORBIDDEN")
    st = path.stat()
    if st.st_uid != 0 or st.st_gid != 0 or (st.st_mode & 0o022):
        raise Stop("HELPER_OWNERSHIP_OR_MODE_UNSAFE")
    actual = sha(path)
    if expected_sha is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or actual != expected_sha:
            raise Stop("HELPER_SHA256_MISMATCH")
    return actual


def ensure_policy(expected_sha):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha or ""):
        raise Stop("POLICY_SHA256_REQUIRED")
    path = Path(POLICY)
    if path.is_symlink() or not path.is_file():
        raise Stop("POLICY_FILE_MISSING_OR_SYMLINK")
    st = path.stat()
    if st.st_uid != 0 or st.st_gid != 0 or (st.st_mode & 0o777) != 0o440:
        raise Stop("POLICY_OWNERSHIP_OR_MODE_UNSAFE")
    if sha(path) != expected_sha:
        raise Stop("POLICY_SHA256_MISMATCH")
    return expected_sha


def execute(argv, input_bytes=b""):
    command = validate_request(argv, input_bytes)
    try:
        return subprocess.run(command, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env={"PATH": TRUSTED_PATH, "LC_ALL": "C", "LANG": "C"},
                              timeout=COMMAND_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Stop("HELPER_COMMAND_TIMEOUT") from exc


def require_ok(proc, label):
    if proc.returncode != 0:
        raise Stop("PREFLIGHT_COMMAND_FAILED_" + label)
    return proc.stdout


def preflight(expected_sha, expected_policy_sha, run_id):
    actual = ensure_context(expected_sha)
    policy_sha = ensure_policy(expected_policy_sha)
    pid_raw = current_haproxy_pid()

    checks = []
    checks.append(("cmdline", execute([trusted_binary("cat"), "/proc/" + pid_raw + "/cmdline"])))

    find_argv = [trusted_binary("find"), CFGDIR, "-maxdepth", "1", "-name", "*.cfg", "!", "-name", ".*", "-print"]
    found = execute(find_argv)
    checks.append(("config_files", found))
    require_ok(found, "CONFIG_FILES")
    entries = sorted(x for x in found.stdout.decode(errors="strict").splitlines() if x)
    checks.append(("config_hashes", execute([trusted_binary("sha256sum"), "--", CONFIG, *entries])))
    checks.append(("stats", execute([trusted_binary("socat"), "-T", "1", "-", "UNIX-CONNECT:" + SOCKET], b"show stat\n")))
    checks.append(("tables", execute([trusted_binary("nft"), "-j", "list", "tables"])))
    checks.append(("firewalld", execute([trusted_binary("nft"), "-s", "-j", "list", "table", "inet", "firewalld"])))
    checks.append(("nft_check", execute([trusted_binary("nft"), "-c", "-f", "-"], rules(run_id))))

    failures = [name for name, proc in checks if proc.returncode != 0]
    if failures:
        raise Stop("PREFLIGHT_COMMAND_FAILED_" + ",".join(failures))
    return {
        "status": "PRIVILEGE_READY",
        "helper_sha256": actual,
        "policy_sha256": policy_sha,
        "run_id": run_id,
        "haproxy_pid": int(pid_raw),
        "checks": [name for name, _ in checks],
        "mutation": "NOT_RUN",
    }


def main():
    try:
        if len(sys.argv) == 5 and sys.argv[1] == "--preflight":
            print(json.dumps(preflight(sys.argv[2], sys.argv[3], sys.argv[4]), sort_keys=True))
            return 0
        if (len(sys.argv) >= 7 and sys.argv[1] == "--expected-sha"
                and sys.argv[3] == "--expected-policy-sha" and sys.argv[5] == "--"):
            ensure_context(sys.argv[2])
            ensure_policy(sys.argv[4])
            payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(payload) > MAX_INPUT_BYTES:
                raise Stop("STDIN_TOO_LARGE")
            proc = execute(sys.argv[6:], payload)
            sys.stdout.buffer.write(proc.stdout)
            sys.stderr.buffer.write(proc.stderr)
            return proc.returncode
        raise Stop("INVALID_HELPER_INVOCATION")
    except (Exception, KeyboardInterrupt) as exc:
        print("STOP: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
