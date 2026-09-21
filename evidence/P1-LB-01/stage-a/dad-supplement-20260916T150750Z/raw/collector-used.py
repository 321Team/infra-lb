#!/usr/bin/env python3
"""P1-LB-01 current-snapshot DAD evidence collector; Python standard library only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = "1.1"
HOST = "k8s-api-lb01"
IFACE = "ens160"
TARGET = "10.1.93.109"
PEER = "10.1.93.254"
APPROVAL = "https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5699238203"
TRUSTED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
ENV = {"PATH": TRUSTED_PATH, "LC_ALL": "C", "LANG": "C"}


class Stop(Exception):
    pass


def stamp():
    now = dt.datetime.now(dt.timezone.utc)
    return {"utc": now.isoformat(), "kst": now.astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat()}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tools_available():
    result = {}
    for name in ("ip", "ss", "systemctl", "arping", "sudo", "env", "timeout"):
        path = shutil.which(name, path=TRUSTED_PATH)
        if not path:
            raise Stop("MISSING_TOOL: " + name + "; no package was installed")
        result[name] = str(Path(path).resolve())
    return result


def tool_metadata(binaries):
    """Binary hashes are auxiliary; evidence/package hashes remain mandatory."""
    result = {}
    for name, path in binaries.items():
        info = Path(path).stat()  # Missing paths or other stat failures still stop.
        entry = {"path": path, "mode": oct(info.st_mode & 0o7777),
                 "uid": info.st_uid, "gid": info.st_gid, "size": info.st_size,
                 "executable_for_login_user": os.access(path, os.X_OK),
                 "sha256": None, "hash_status": "PENDING"}
        try:
            entry["sha256"] = sha(path)
            entry["hash_status"] = "COLLECTED"
        except PermissionError as exc:
            # Execution permission and read permission differ. Do not change
            # permissions or elevate a file read just for this optional hash.
            entry["hash_status"] = "UNAVAILABLE_PERMISSION_DENIED"
            entry["hash_error"] = {"type": type(exc).__name__, "errno": exc.errno,
                                   "message": str(exc)}
        result[name] = entry
    return result


class Runner:
    def __init__(self, folder, tools):
        self.folder = Path(folder)
        self.tools = tools
        self.records = []

    def run(self, name, args, privileged=False):
        # Each label has exclusive log files: accidental duplicate execution fails closed.
        command = [self.tools[args[0]], *args[1:]]
        if privileged:
            command = [self.tools["sudo"], "-n", "--", self.tools["env"], "-i",
                       "PATH=" + TRUSTED_PATH, "LC_ALL=C", "LANG=C",
                       self.tools["timeout"], "--signal=TERM", "--kill-after=2s", "10s", *command]
        stdout_path = self.folder / (name + ".stdout.txt")
        stderr_path = self.folder / (name + ".stderr.txt")
        record = {"name": name, "argv": command, "started": stamp(),
                  "privileged": privileged, "return_code": None, "outer_timeout": False}
        start = time.monotonic()
        with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
            try:
                p = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   env=ENV, timeout=18 if privileged else 6, check=False)
                record["return_code"] = p.returncode
            except subprocess.TimeoutExpired:
                record["outer_timeout"] = True
                record["execution_error"] = "outer timeout; no successful arping RC inferred"
            except KeyboardInterrupt:
                record["execution_error"] = "operator interrupted command; no successful RC inferred"
            except OSError as exc:
                record["execution_error"] = str(exc)
        record["finished"] = stamp()
        record["duration_seconds"] = round(time.monotonic() - start, 6)
        record["stdout_file"] = stdout_path.name
        record["stderr_file"] = stderr_path.name
        self.records.append(record)
        write_json(self.folder / "COMMANDS.json", self.records)
        return {**record, "stdout": stdout_path.read_bytes().decode("utf-8", "replace"),
                "stderr": stderr_path.read_bytes().decode("utf-8", "replace")}


def require_ok(record):
    if record.get("outer_timeout") or record.get("execution_error") or record["return_code"] != 0:
        raise Stop("COMMAND_FAILED: " + record["name"])
    if record["stderr"].strip():
        raise Stop("COMMAND_STDERR_REQUIRES_REVIEW: " + record["name"])
    return record["stdout"]


def json_output(record):
    try:
        return json.loads(require_ok(record))
    except (ValueError, TypeError) as exc:
        raise Stop("INVALID_JSON: " + record["name"]) from exc


def snapshot(runner, phase):
    # Collect all four even when one fails, preserving diagnostics for reviewer.
    records = {
        "addr": runner.run(phase + "_ip_address", ["ip", "-j", "-4", "addr", "show", "dev", IFACE]),
        "link": runner.run(phase + "_ip_link", ["ip", "-j", "link", "show", "dev", IFACE]),
        "service": runner.run(phase + "_haproxy", ["systemctl", "is-active", "haproxy.service"]),
        "listen": runner.run(phase + "_listeners", ["ss", "-H", "-lnt"]),
    }
    addr = json_output(records["addr"])
    link = json_output(records["link"])
    if not isinstance(addr, list) or len(addr) != 1 or not isinstance(link, list) or len(link) != 1:
        raise Stop("UNEXPECTED_INTERFACE_DATA: " + phase)
    a, l = addr[0], link[0]
    if a.get("ifname") != IFACE or l.get("ifname") != IFACE:
        raise Stop("WRONG_INTERFACE: " + phase)
    flags = set(l.get("flags", []))
    if not {"UP", "LOWER_UP", "BROADCAST"}.issubset(flags) or "NOARP" in flags:
        raise Stop("LINK_NOT_READY: " + phase)
    if l.get("operstate") != "UP" or l.get("link_type") != "ether":
        raise Stop("LINK_NOT_ETHERNET_UP: " + phase)
    mac = str(l.get("address", "")).lower()
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac) or mac == "00:00:00:00:00:00":
        raise Stop("INVALID_MAC: " + phase)
    ips = [x for x in a.get("addr_info", []) if x.get("family") == "inet" and x.get("scope") == "global"]
    if len(ips) != 1 or ips[0].get("local") != TARGET or ips[0].get("prefixlen") != 24:
        raise Stop("EXPECTED_SINGLE_IPV4_MISSING: " + phase)
    if any(ips[0].get(k) for k in ("tentative", "dadfailed", "deprecated")):
        raise Stop("ADDRESS_NOT_READY: " + phase)
    if require_ok(records["service"]).strip() != "active":
        raise Stop("HAPROXY_NOT_ACTIVE: " + phase)
    listeners = require_ok(records["listen"])
    if not any(len(p := line.split()) >= 5 and p[0] == "LISTEN" and p[3] == TARGET + ":6443"
               for line in listeners.splitlines()):
        raise Stop("EXPECTED_LISTENER_MISSING: " + phase)
    return {"interface": IFACE, "ipv4": TARGET, "prefixlen": 24, "mac": mac,
            "haproxy": "active", "listener": TARGET + ":6443", "link": "UP"}


def parse_arping(record, expected_target, expected_source):
    output = record["stdout"]
    sent = re.findall(r"^Sent\s+(\d+)\s+probes?\b", output, re.M)
    received = re.findall(r"^Received\s+(\d+)\s+response", output, re.M)
    headers = re.findall(r"^ARPING\s+(\d+\.\d+\.\d+\.\d+)\s+from\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)", output, re.M)
    valid = (len(sent) == len(received) == len(headers) == 1
             and headers[0] == (expected_target, expected_source, IFACE))
    macs = sorted(set(m.lower() for m in re.findall(r"\[((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})\]", output)))
    return {"summary_valid": valid, "sent": int(sent[0]) if len(sent) == 1 else None,
            "received": int(received[0]) if len(received) == 1 else None, "reply_macs": macs,
            "wrapper_return_code": record["return_code"],
            "arping_return_code": record["return_code"] if valid and not record.get("outer_timeout")
            and not record.get("execution_error") and record["return_code"] in (0, 1) else None}


def inspect(runner, hostname):
    result = {"status": "STOP", "scope": "CURRENT_SNAPSHOT_ONLY", "historical_original_recovered": False,
              "final_acceptance": "PENDING_REVIEW", "dad_attempted": False, "reasons": []}
    packets_attempted = False
    before = None
    try:
        if hostname.split(".", 1)[0] != HOST:
            raise Stop("WRONG_HOST: expected " + HOST)
        version = runner.run("01_arping_version", ["arping", "-V"], privileged=True)
        if "iputils" not in require_ok(version).lower():
            raise Stop("UNSUPPORTED_ARPING_IMPLEMENTATION")
        before = snapshot(runner, "02_before")
        result["before"] = before
        route = json_output(runner.run("03_peer_route", ["ip", "-j", "-4", "route", "get", PEER]))
        if (not isinstance(route, list) or len(route) != 1 or route[0].get("dev") != IFACE
                or route[0].get("prefsrc") != TARGET or route[0].get("gateway")
                or route[0].get("type", "unicast") != "unicast"):
            raise Stop("PEER_NOT_DIRECTLY_REACHABLE_ON_EXPECTED_INTERFACE")
        packets_attempted = True
        peer = runner.run("04_l2_peer", ["arping", "-b", "-f", "-c", "1", "-I", IFACE,
                                        "-s", TARGET, PEER], privileged=True)
        result["l2_peer"] = parse_arping(peer, PEER, TARGET)
        require_ok(peer)
        if (not result["l2_peer"]["summary_valid"] or result["l2_peer"]["sent"] != 1
                or result["l2_peer"]["received"] < 1 or not result["l2_peer"]["reply_macs"]):
            raise Stop("L2_PEER_NOT_CONFIRMED")
        result["dad_attempted"] = True
        dad = runner.run("05_dad", ["arping", "-D", "-c", "3", "-I", IFACE, TARGET], privileged=True)
        result["dad"] = parse_arping(dad, TARGET, "0.0.0.0")
        d = result["dad"]
        if d["received"] is not None and d["received"] > 0:
            result["status"] = "FAIL_CONFLICT_SUSPECTED_REVIEW_REQUIRED"
            result["reasons"].append("DAD_RESPONSE_RECEIVED: inspect reply MACs; no automatic own-MAC exclusion")
        else:
            require_ok(dad)
            if (not d["summary_valid"] or d["sent"] != 3 or d["received"] != 0
                    or d["arping_return_code"] != 0 or d["reply_macs"]):
                raise Stop("DAD_OUTPUT_INCOMPLETE_OR_INCONSISTENT")
            result["status"] = "PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED"
    except Stop as exc:
        result["status"] = "STOP"
        result["reasons"].append(str(exc))
    except Exception as exc:
        result["status"] = "STOP"
        result["reasons"].append("COLLECTION_ERROR: " + type(exc).__name__ + ": " + str(exc))
    finally:
        if packets_attempted:
            try:
                after = snapshot(runner, "06_after")
                result["after"] = after
                if after != before:
                    raise Stop("STATE_CHANGED_DURING_CHECK")
                result["postcheck"] = "MATCH"
            except Exception as exc:
                result["postcheck"] = "FAILED"
                result["status"] = "STOP"
                result["reasons"].append("POSTCHECK: " + str(exc))
    return result


def package(folder):
    folder = Path(folder)
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (folder / "SHA256SUMS").write_text("".join(sha(p) + "  " + p.name + "\n" for p in files), encoding="ascii")
    archive = folder.with_name(folder.name + ".tar.gz")
    with tarfile.open(archive, "x:gz") as tar:
        tar.add(folder, arcname=folder.name, recursive=True)
    sidecar = archive.with_name(archive.name + ".sha256")
    with sidecar.open("x", encoding="ascii") as f:
        f.write(sha(archive) + "  " + archive.name + "\n")
    return archive, sidecar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="perform the approved current-snapshot check once")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        return 2
    if os.getuid() == 0 or os.geteuid() == 0:
        print("STOP: run as your regular LB login user, after sudo -v. Do not use sudo python3.", file=sys.stderr)
        return 2
    os.umask(0o077)
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir).resolve()
    if not home.is_dir() or home.stat().st_uid != os.getuid():
        print("STOP: account home directory is unavailable or has unexpected ownership.", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_DAD_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_", dir=home))
    metadata = {"kit_version": VERSION, "approval_url": APPROVAL, "started": stamp(),
                "hostname": socket.gethostname(), "user": account.pw_name, "uid": os.getuid(),
                "home": str(home), "kernel": list(os.uname()), "evidence_directory": str(folder),
                "historical_source_gap": "2026-08-31 original remains unavailable; no backdating",
                "purpose": "current-snapshot supplementary DAD check"}
    write_json(folder / "METADATA.json", metadata)
    shutil.copyfile(Path(__file__).resolve(), folder / "collector-used.py")
    try:
        binaries = tools_available()
        inventory = tool_metadata(binaries)
        write_json(folder / "TOOLS.json", inventory)
        result = inspect(Runner(folder, binaries), metadata["hostname"])
        result["tool_hash_unavailable"] = [name for name, entry in inventory.items()
                                           if entry["hash_status"] != "COLLECTED"]
    except Exception as exc:
        result = {"status": "STOP", "scope": "CURRENT_SNAPSHOT_ONLY", "dad_attempted": False,
                  "final_acceptance": "PENDING_REVIEW", "reasons": [str(exc)]}
    result["finished"] = stamp()
    result["approval_url"] = APPROVAL
    write_json(folder / "RESULT.json", result)
    try:
        archive, sidecar = package(folder)
    except Exception as exc:
        print("STOP: packaging failed; keep original evidence directory: " + str(folder), file=sys.stderr)
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 2
    print("STATUS=" + result["status"])
    for reason in result.get("reasons", []):
        print("REASON=" + reason)
    print("EVIDENCE_DIR=" + str(folder))
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    print("Return the ARCHIVE and SIDECAR for verification and receiver review.")
    return 0 if result["status"] == "PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    sys.exit(main())
