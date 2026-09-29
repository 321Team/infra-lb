#!/usr/bin/env python3
"""Read-only readiness: existing LB SSH identity from ansible01, or nft --check on LB."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import uuid

from collect_preflight import Stop, json_output, require_ok, sha, stamp, write_json
from stageb_common import RuntimeRunner, binaries
from stageb_rules import PREFIX, rules, table_name, table_rows

LB_USER = "server01_k8s--api-lb"
IDENTITY = ("import json,os,pwd,socket; p=pwd.getpwuid(os.getuid()); "
            "print(json.dumps(dict(host=socket.gethostname().split('.')[0],user=p.pw_name,"
            "uid=os.getuid(),euid=os.geteuid())))")


def verify_identity(value):
    if (not isinstance(value, dict) or value.get("host") != "k8s-api-lb01" or value.get("user") != LB_USER
            or type(value.get("uid")) is not int or value["uid"] <= 0 or value.get("euid") != value["uid"]):
        raise Stop("LB_IDENTITY_MISMATCH")
    return value


def parse_ansible_result(path):
    result = json.loads(path.read_text())
    if result.get("unreachable") or result.get("failed") or result.get("rc") != 0:
        raise Stop("LB_SSH_NOT_CONFIRMED_NO_ACCESS_CHANGE_ATTEMPTED")
    if result.get("stderr", "").strip():
        raise Stop("LB_IDENTITY_STDERR_REQUIRES_REVIEW")
    return verify_identity(json.loads(result["stdout"]))


def ansible_args(executable, folder, private_key):
    # Inline one-host inventory is a temporary connection description only.
    # Existing p1-ans-01 inventory, SSH keys and remote accounts are not changed.
    extra = {"ansible_user": LB_USER, "ansible_become": False, "ansible_python_interpreter": "/usr/bin/python3",
             "ansible_ssh_use_tty": False,
             "ansible_ssh_common_args": "-o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o RequestTTY=no -o ConnectionAttempts=1 -o ConnectTimeout=5 -o ClearAllForwardings=yes -o PermitLocalCommand=no -o RemoteCommand=none"}
    return [executable, "10.1.93.109", "-i", "10.1.93.109,", "-c", "ssh", "-u", LB_USER,
            "--private-key", str(private_key), "-e", json.dumps(extra), "-m", "ansible.builtin.command", "-a", json.dumps({"argv": ["/usr/bin/python3", "-c", IDENTITY]}),
            "--tree", str(folder / "ansible-result")]


def inspect_ansible(folder, home, private_key_arg):
    project = home / "p1-ans-01"
    config, inventory = project / "ansible.cfg", project / "inventory/hosts.yml"
    if not config.is_file() or not inventory.is_file():
        raise Stop("EXISTING_ANSIBLE_PROJECT_MISSING")
    if not private_key_arg:
        raise Stop("ANSIBLE_PRIVATE_KEY_REQUIRED")
    private_key = Path(private_key_arg).expanduser()
    if not private_key.is_absolute() or private_key.is_symlink() or not private_key.is_file():
        raise Stop("ANSIBLE_PRIVATE_KEY_INVALID")
    key_stat = private_key.stat()
    if key_stat.st_uid != os.getuid() or (key_stat.st_mode & 0o077):
        raise Stop("ANSIBLE_PRIVATE_KEY_OWNER_OR_MODE_INVALID")
    if not os.access(private_key, os.R_OK):
        raise Stop("ANSIBLE_PRIVATE_KEY_NOT_READABLE")
    exe = shutil.which("ansible")
    if not exe:
        raise Stop("ANSIBLE_NOT_FOUND_SOURCE_EXISTING_ENV_FIRST")
    env = dict(os.environ, ANSIBLE_CONFIG=str(config), ANSIBLE_HOST_KEY_CHECKING="True",
               ANSIBLE_NOCOLOR="1", ANSIBLE_TIMEOUT="5", ANSIBLE_SSH_USETTY="false",
               ANSIBLE_SSH_ARGS="-o ControlMaster=no -o ControlPath=none -o ControlPersist=no")
    command = ansible_args(exe, folder, private_key)
    write_json(folder / "COMMAND.json", {"argv": command, "started": stamp(),
               "config_sha256": sha(config), "inventory_sha256": sha(inventory),
               "inventory_contents_collected": False, "ssh_credentials_collected": False,
               "private_key_path": str(private_key), "private_key_contents_collected": False,
               "connection_scope": "existing SSH authentication only, fixed LB ordinary account, explicit existing private key"})
    with (folder / "ansible.stdout.txt").open("xb") as out, (folder / "ansible.stderr.txt").open("xb") as err:
        proc = subprocess.Popen(command, cwd=project, env=env, stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=30)
        except BaseException:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            write_json(folder / "EXECUTION.json", {"return_code": proc.returncode, "interrupted_or_timeout": True, "finished": stamp()})
            raise
    write_json(folder / "EXECUTION.json", {"return_code": proc.returncode, "finished": stamp()})
    raw = folder / "ansible-result" / "10.1.93.109"
    if not raw.is_file():
        raise Stop("ANSIBLE_DID_NOT_RETURN_HOST_RESULT")
    shutil.copyfile(raw, folder / "LB_IDENTITY_RESULT.json")
    identity = parse_ansible_result(raw)
    if proc.returncode != 0:
        raise Stop("ANSIBLE_NONZERO_RETURN_CODE")
    return {"status": "LB_SSH_IDENTITY_CONFIRMED", "identity": identity,
            "sudo": "NOT_TESTED", "runtime": "NOT_RUN", "new_credentials_or_permissions": False}


def inspect_nft(runner, folder, run_id):
    batch = rules(run_id)
    (folder / "CANDIDATE_CHECK_ONLY.nft").write_bytes(batch)
    before = json_output(runner.run("01_tables_before", ["nft", "-j", "list", "tables"], True))
    rows = table_rows(before)
    if any(x["name"].startswith(PREFIX) for x in rows):
        raise Stop("EXISTING_STAGEB_TABLE_REQUIRES_REVIEW")
    if not any(x["name"] == "firewalld" and x["family"] == "inet" for x in rows):
        raise Stop("FIREWALLD_TABLE_MISSING")
    before_rules = json_output(runner.run("02_rules_before", ["nft", "-s", "-j", "list", "ruleset"], True))
    require_ok(runner.run("03_nft_version", ["nft", "--version"]))
    failure = None
    try:
        # --check validates without applying; the input batch is never submitted without -c.
        require_ok(runner.run("04_nft_check_only", ["nft", "-c", "-f", "-"], True, batch))
    except Exception as exc:
        failure = exc
    after = json_output(runner.run("05_tables_after", ["nft", "-j", "list", "tables"], True))
    after_rows = table_rows(after)
    after_rules = json_output(runner.run("06_rules_after", ["nft", "-s", "-j", "list", "ruleset"], True))
    if any(x["name"] == table_name(run_id) for x in after_rows) or before != after or before_rules != after_rules:
        raise Stop("NFT_STATE_CHANGED_DURING_READONLY_CHECK_PRESERVE_EVIDENCE")
    if failure:
        raise failure
    return {"status": "NFT_CHECK_ONLY_PASS", "rules_sha256": sha(folder / "CANDIDATE_CHECK_ONLY.nft"),
            "stateless_rules_before_after": "MATCH", "candidate_table": "ABSENT",
            "fault_injection": "NOT_RUN", "actual_expiry_and_recovery": "NOT_TESTED"}


def package(folder):
    # Only declared top-level originals; no sockets or unmanifested nested files.
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and p.name != "SHA256SUMS")
    (folder / "SHA256SUMS").write_text("".join(sha(p) + "  " + p.name + "\n" for p in files))
    archive = folder.with_name(folder.name + ".tar.gz")
    with tarfile.open(archive, "x:gz") as tar:
        for p in files + [folder / "SHA256SUMS"]:
            tar.add(p, arcname=folder.name + "/" + p.name, recursive=False)
    sidecar = archive.with_name(archive.name + ".sha256")
    with sidecar.open("x") as f:
        f.write(sha(archive) + "  " + archive.name + "\n")
    return archive, sidecar


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--role", choices=["ansible", "lb"], required=True)
    p.add_argument("--private-key", help="Existing ansible01 SSH private key path; required only for --role ansible")
    p.add_argument("--run", action="store_true")
    args = p.parse_args()
    account = pwd.getpwuid(os.getuid())
    expected = ("ansible01", "server01_ansible") if args.role == "ansible" else ("k8s-api-lb01", LB_USER)
    if (not args.run or (socket.gethostname().split(".")[0], account.pw_name) != expected
            or os.getuid() == 0 or os.getuid() != os.geteuid()):
        raise Stop("WRONG_HOST_ACCOUNT_OR_MISSING_RUN_FLAG")
    home = Path(account.pw_dir).resolve()
    if home.stat().st_uid != os.getuid():
        raise Stop("HOME_OWNERSHIP_MISMATCH")
    os.umask(0o077)
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_READINESS_" + args.role.upper() + "_", dir=home))
    print("EVIDENCE_DIR=" + str(folder), flush=True)
    write_json(folder / "METADATA.json", {"started": stamp(), "role": args.role, "host": expected[0], "user": account.pw_name,
               "scope": "READ_ONLY_PRECHECK", "source_revision": Path(__file__).with_name("SOURCE_REVISION").read_text().strip(),
               "credential_contents_collected": False})
    for name in ["collect_stageb_readiness.py", "collect_preflight.py", "stageb_common.py", "stageb_rules.py"]:
        shutil.copyfile(Path(__file__).with_name(name), folder / name)
    try:
        if args.role == "ansible":
            result = inspect_ansible(folder, home, args.private_key)
        else:
            if args.private_key:
                raise Stop("PRIVATE_KEY_NOT_ALLOWED_FOR_LB_ROLE")
            runner = RuntimeRunner(folder, binaries(["nft", "sudo", "env", "timeout"]), seconds=5)
            result = inspect_nft(runner, folder, uuid.uuid4().hex)
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "STOP", "reason": type(exc).__name__ + ": " + str(exc), "runtime": "NOT_RUN"}
    result["finished"] = stamp()
    write_json(folder / "RESULT.json", result)
    archive, sidecar = package(folder)
    print("STATUS=" + result["status"])
    if "reason" in result:
        print("REASON=" + result["reason"])
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    return 2 if result["status"] == "STOP" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("STOP: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(2)
