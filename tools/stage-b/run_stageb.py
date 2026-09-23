#!/usr/bin/env python3
"""Run from ansible01. Default --check-access is read-only; --run is explicit Runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import uuid

from collect_preflight import Stop, package, sha, stamp, write_json
from stageb_common import source_files, validate_inputs


def verify_delivery(root):
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        raise Stop("EXTRACT_THE_COMPLETE_REVIEW_KIT_FIRST")
    seen = set()
    for line in manifest.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = root / name
        if (name in seen or not re.fullmatch(r"[0-9a-f]{64}", digest) or path.is_symlink()
                or path.resolve().parent != root and root not in path.resolve().parents):
            raise Stop("INVALID_DELIVERY_MANIFEST")
        if not path.is_file() or sha(path) != digest:
            raise Stop("DELIVERY_HASH_MISMATCH_" + name)
        seen.add(name)
    required = set(source_files() + ["run_stageb.py", "SOURCE_REVISION", "ansible/runtime.yml", "ansible/poll.yml", "ansible/fetch.yml"])
    if not required <= seen:
        raise Stop("DELIVERY_MANIFEST_MISSING_REQUIRED_SOURCE")


def verify_archive(archive, sidecar, run_id):
    expected_name = "P1_LB_STAGEB_" + run_id + ".tar.gz"
    if sidecar.read_text().strip() != sha(archive) + "  " + expected_name:
        raise Stop("REMOTE_ARCHIVE_SIDECAR_MISMATCH")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        prefix = "P1_LB_STAGEB_" + run_id + "/"
        if len(members) > 3000 or sum(m.size for m in members) > 64 * 1024 * 1024:
            raise Stop("REMOTE_ARCHIVE_LIMIT_EXCEEDED")
        contents = {}
        for m in members:
            if not m.isfile() or not m.name.startswith(prefix):
                raise Stop("INVALID_ARCHIVE_MEMBER")
            name = m.name[len(prefix):]
            if not name or "/" in name or name in {".", ".."} or name in contents:
                raise Stop("ARCHIVE_PATH_OR_DUPLICATE")
            contents[name] = tar.extractfile(m).read()
        manifest = {}
        for line in contents.pop("SHA256SUMS").decode("ascii").splitlines():
            digest, name = line.split("  ", 1)
            if name in manifest or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise Stop("INVALID_MANIFEST")
            manifest[name] = digest
        if {n: hashlib.sha256(b).hexdigest() for n, b in contents.items()} != manifest:
            raise Stop("REMOTE_MANIFEST_MISMATCH")
    return contents


def classify(folder, data, rc):
    result = dict(status="STOP", ansible_rc=rc, stage_b="NOT_COMPLETED", final_acceptance="PENDING")
    try:
        evidence = {role: verify_archive(folder / (role + ".tar.gz"),
                     folder / (role + ".tar.gz.sha256"), data["run_id"]) for role in ("cp", "lb")}
        for role, content in evidence.items():
            if json.loads(content["INPUTS.json"]) != data:
                raise Stop("REMOTE_INPUTS_MISMATCH_" + role)
            for name, digest in data["source_hashes"].items():
                if hashlib.sha256(content["source_" + name]).hexdigest() != digest:
                    raise Stop("REMOTE_SOURCE_MISMATCH_" + role)
        result["archive_integrity"] = "PASS"
        cp_state = json.loads(evidence["cp"]["STATE.json"])
        lb_result = json.loads(evidence["lb"]["RESULT.json"])
        samples = [json.loads(x) for x in evidence["cp"]["SAMPLES.jsonl"].splitlines()]
        if (rc != 0 or cp_state["status"] != "OBSERVER_COMPLETE" or lb_result["status"] != "PASS_CANDIDATE"
                or len(samples) < 40 or not all(s["success"] for s in samples)
                or [s["sequence"] for s in samples] != list(range(1, len(samples) + 1))):
            raise Stop("RUNTIME_OUTCOME_OR_SAMPLES_NOT_PASS_CANDIDATE")
        result.update(status="PASS_CANDIDATE", sample_count=len(samples), lb_result=lb_result,
                      caveat="Review raw timeline and coverage; no SLA, reboot or final acceptance claim")
    except Exception as exc:
        result["reason"] = type(exc).__name__ + ": " + str(exc)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-access", action="store_true")
    mode.add_argument("--run", action="store_true")
    p.add_argument("--lb-inventory", type=Path, required=True, help="existing approved inventory containing k8s-api-lb01; no credentials created")
    p.add_argument("--lb-user", help="existing LB account for --check-access")
    p.add_argument("--inputs", type=Path, help="nonsecret completed Runtime input JSON")
    args = p.parse_args()
    account = pwd.getpwuid(os.getuid())
    if (socket.gethostname().split(".")[0], account.pw_name) != ("ansible01", "server01_ansible") or os.getuid() == 0:
        raise Stop("RUN_FROM_ANSIBLE01_SERVER01_ANSIBLE")
    root = Path(__file__).resolve().parent
    verify_delivery(root)
    home = Path(account.pw_dir).resolve()
    project = home / "p1-ans-01"
    for path in [project / "inventory/hosts.yml", project / "ansible.cfg", args.lb_inventory]:
        if not path.is_file():
            raise Stop("EXISTING_INVENTORY_OR_CONFIG_MISSING: " + str(path))
    if args.run:
        if not args.inputs:
            raise Stop("COMPLETED_INPUTS_REQUIRED")
        data = json.loads(args.inputs.read_text())
        # Local delivery manifest pins repository files; delivery metadata contains the resulting commit.
        revision = (root / "SOURCE_REVISION").read_text().strip()
        if data.get("source_revision") != revision:
            raise Stop("INPUT_SOURCE_DIFFERS_FROM_DELIVERY_REVISION")
        data["run_id"] = uuid.uuid4().hex
        data["source_hashes"] = {n: sha(root / n) for n in source_files()}
        validate_inputs(data)
    else:
        if not args.lb_user or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", args.lb_user) or args.lb_user == "root":
            raise Stop("EXISTING_NONROOT_LB_USER_REQUIRED")
        data = {"lb_user": args.lb_user}
    os.umask(0o077)
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_STAGEB_CONTROLLER_", dir=home))
    write_json(folder / "INPUTS.json", data)
    for name in ["run_stageb.py", "SOURCE_REVISION", "SHA256SUMS", "ansible/runtime.yml", "ansible/poll.yml", "ansible/fetch.yml"]:
        shutil.copyfile(root / name, folder / ("controller_source_" + name.replace("/", "_")))
    write_json(folder / "METADATA.json", {"started": stamp(), "mode": "RUNTIME" if args.run else "ACCESS_ONLY",
               "inventory_sha256": sha(project / "inventory/hosts.yml"), "lb_inventory_sha256": sha(args.lb_inventory),
               "ansible_config_sha256": sha(project / "ansible.cfg"), "inventory_contents_collected": False})
    extra = folder / "VARS.json"
    write_json(extra, {"inputs": data, "evidence_dir": str(folder), "ansible_become": False})
    command = ["ansible-playbook", "-i", str(project / "inventory/hosts.yml"), "-i", str(args.lb_inventory.resolve()),
               str(root / "ansible/runtime.yml"), "--extra-vars", "@" + str(extra)]
    if args.check_access:
        command += ["--tags", "access"]
    env = dict(os.environ, ANSIBLE_CONFIG=str(project / "ansible.cfg"), ANSIBLE_HOST_KEY_CHECKING="True",
               ANSIBLE_NOCOLOR="1", ANSIBLE_TIMEOUT="5", PYTHONDONTWRITEBYTECODE="1")
    rc = 2
    try:
        with (folder / "ansible.stdout.txt").open("wb") as out, (folder / "ansible.stderr.txt").open("wb") as err:
            proc = subprocess.Popen(command, cwd=project, env=env, stdout=out, stderr=err,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                rc = proc.wait(timeout=480 if args.run else 60)
            except BaseException:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
                raise
    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        write_json(folder / "CONTROLLER_ERROR.json", {"error": str(exc), "recovery": "LB lease expiry and 60s kernel timeout; verify own table removal via OOB"})
    result = classify(folder, data, rc) if args.run else {"status": "ACCESS_CONFIRMED" if rc == 0 else "STOP", "runtime": "NOT_RUN", "ansible_rc": rc}
    write_json(folder / "RESULT.json", result)
    archive, sidecar = package(folder)
    print("STATUS=" + result["status"])
    print("EVIDENCE_DIR=" + str(folder))
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    return 0 if result["status"] in {"ACCESS_CONFIRMED", "PASS_CANDIDATE"} else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("STOP: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(2)
