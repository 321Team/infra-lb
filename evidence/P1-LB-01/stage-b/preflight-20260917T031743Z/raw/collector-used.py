#!/usr/bin/env python3
"""P1-LB-01 bounded, read-only LB preflight. Python 3.8+ standard library."""
import argparse
import csv
import datetime as dt
import hashlib
import io
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

VERSION = "1.0"
HOST = "k8s-api-lb01"
IFACE = "ens160"
TARGET = "10.1.93.109"
TRUSTED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
ENV = {"PATH": TRUSTED_PATH, "LC_ALL": "C", "LANG": "C"}
CONFIG = "/etc/haproxy/haproxy.cfg"
BASELINE_CONFIG_SHA256 = "afd19086ab8529d621185c231fa3c588eaeeb2025a08445e90f28cf27b00504f"
CFGDIR = "/etc/haproxy/conf.d"
SOCKET = "/var/lib/haproxy/stats"
BACKEND = "kubernetes_api_backend"
SERVERS = {"k8s-control01": "10.1.93.102", "k8s-control02": "10.1.93.103", "k8s-control03": "10.1.93.104"}
EXPECTED_ARGV = ["/usr/sbin/haproxy", "-Ws", "-f", CONFIG, "-f", CFGDIR, "-p", "/run/haproxy.pid"]

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


def tools_available():
    result = {}
    for name in ("ip", "ss", "systemctl", "cat", "sha256sum", "find", "haproxy", "sudo", "env", "timeout", "socat"):
        path = shutil.which(name, path=TRUSTED_PATH)
        if not path:
            if name == "socat":
                continue
            raise Stop("MISSING_TOOL: " + name + "; no installation attempted")
        result[name] = str(Path(path).resolve())
    if result["haproxy"] != "/usr/sbin/haproxy":
        raise Stop("UNEXPECTED_HAPROXY_BINARY")
    return result


class Runner:
    def __init__(self, folder, tools):
        self.folder, self.tools, self.records = Path(folder), tools, []

    def run(self, name, args, privileged=False, input_bytes=None):
        command = [self.tools[args[0]], *args[1:]]
        if privileged:
            command = [self.tools["sudo"], "-n", "--", self.tools["env"], "-i",
                       "PATH=" + TRUSTED_PATH, "LC_ALL=C", "LANG=C",
                       self.tools["timeout"], "--signal=TERM", "--kill-after=2s", "10s", *command]
        record = {"name": name, "argv": command, "privileged": privileged,
                  "stdin": input_bytes.decode("ascii") if input_bytes is not None else None,
                  "started": stamp(), "return_code": None, "outer_timeout": False}
        start = time.monotonic()
        outpath, errpath = self.folder / (name + ".stdout.txt"), self.folder / (name + ".stderr.txt")
        with outpath.open("xb") as out, errpath.open("xb") as err:
            kwargs = {"input": input_bytes} if input_bytes is not None else {"stdin": subprocess.DEVNULL}
            try:
                p = subprocess.run(command, stdout=out, stderr=err, env=ENV,
                                   timeout=18 if privileged else 6, check=False, **kwargs)
                record["return_code"] = p.returncode
            except subprocess.TimeoutExpired:
                record["outer_timeout"] = True
                record["execution_error"] = "command exceeded outer timeout"
            except OSError as exc:
                record["execution_error"] = str(exc)
            except KeyboardInterrupt:
                record["execution_error"] = "operator interrupted"
                raise
            finally:
                record["finished"] = stamp()
                record["elapsed_seconds"] = round(time.monotonic() - start, 6)
                self.records.append(record)
                write_json(self.folder / "COMMANDS.json", self.records)
        return {**record, "stdout": outpath.read_bytes().decode("utf-8", "replace"),
                "stderr": errpath.read_bytes().decode("utf-8", "replace")}


def check_cmdline(raw):
    args = raw.rstrip("\0").split("\0")
    if args != EXPECTED_ARGV:
        raise Stop("SERVICE_ARGUMENTS_CHANGED_REVIEW_REQUIRED")
    return args


def config_state(runner, phase):
    pid = require_ok(runner.run(phase + "_pid", ["systemctl", "show", "haproxy.service", "--property=MainPID", "--value"])).strip()
    if not pid.isdigit() or int(pid) <= 1:
        raise Stop("INVALID_HAPROXY_MAIN_PID")
    argv = check_cmdline(require_ok(runner.run(phase + "_cmdline", ["cat", "/proc/" + pid + "/cmdline"], privileged=True)))
    listing = require_ok(runner.run(phase + "_config_files", ["find", CFGDIR, "-maxdepth", "1", "-name", "*.cfg", "!", "-name", ".*", "-print"], privileged=True))
    entries = sorted(listing.splitlines())
    if len(entries) > 100 or len(set(entries)) != len(entries):
        raise Stop("UNEXPECTED_CONFIG_FILE_LIST")
    for p in entries:
        if not re.fullmatch(re.escape(CFGDIR) + r"/[A-Za-z0-9_][A-Za-z0-9_.-]*\.cfg", p):
            raise Stop("UNEXPECTED_CONFIG_FILENAME")
    expected = [CONFIG, *entries]
    hashes = require_ok(runner.run(phase + "_config_hashes", ["sha256sum", "--", *expected], privileged=True))
    mapping = {}
    for line in hashes.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (/.+)", line)
        if not match or match[2] in mapping:
            raise Stop("INVALID_CONFIG_HASH_OUTPUT")
        mapping[match[2]] = match[1]
    if set(mapping) != set(expected):
        raise Stop("INCOMPLETE_CONFIG_HASH_OUTPUT")
    return {"pid": int(pid), "argv": argv, "config_hashes": mapping}


def parse_stats(raw):
    lines = raw.strip().splitlines()
    if not lines or not lines[0].startswith("# pxname,"):
        raise Stop("INVALID_STATS_HEADER")
    lines[0] = lines[0][2:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    required = {"pxname", "svname", "status", "type", "addr", "check_status", "weight", "act", "bck"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise Stop("INCOMPLETE_STATS_FIELDS")
    backend_rows = [row for row in reader if row.get("pxname") == BACKEND]
    rows = [row for row in backend_rows if row.get("svname") != "BACKEND"]
    if len(rows) != 3 or {r.get("svname") for r in rows} != set(SERVERS):
        raise Stop("MISSING_DUPLICATE_OR_EXTRA_BACKEND")
    aggregate = [r for r in backend_rows if r.get("svname") == "BACKEND"]
    if len(aggregate) != 1 or aggregate[0].get("type") != "1":
        raise Stop("MISSING_OR_INVALID_BACKEND_AGGREGATE")
    values = {}
    for row in rows:
        name = row["svname"]
        if row["addr"] != SERVERS[name] + ":6443" or row["type"] != "2":
            raise Stop("BACKEND_IDENTITY_MISMATCH: " + name)
        if not row["weight"].isdigit():
            raise Stop("INVALID_BACKEND_WEIGHT: " + name)
        values[name] = {key: row[key] for key in ("addr", "status", "check_status", "weight", "act", "bck")}
    ready = (aggregate[0].get("status") == "UP" and all(
        r["status"] == "UP" and r["check_status"] == "L4OK" and int(r["weight"]) > 0
        and r["act"] == "1" and r["bck"] == "0" for r in values.values()))
    return {"servers": values, "backend_status": aggregate[0].get("status"), "all_three_up": ready}


def query_stats(runner, phase):
    if "socat" not in runner.tools:
        raise Stop("MISSING_TOOL: socat; existing socket not queried; no installation attempted")
    record = runner.run(phase + "_stats", ["socat", "-T", "3", "-", "UNIX-CONNECT:" + SOCKET],
                        privileged=True, input_bytes=b"show stat\n")
    return parse_stats(require_ok(record))


def tcp_probe(name, ip):
    result = {"server": name, "source_ip": TARGET, "target": ip + ":6443", "started": stamp(),
              "kind": "TCP_CONNECT_ONLY", "connected": False, "timeout_seconds": 3,
              "errno": None, "error": None, "local_socket": None}
    start = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            sock.bind((TARGET, 0))
            result["local_socket"] = list(sock.getsockname())
            sock.connect((ip, 6443))
            result["connected"] = True
    except OSError as exc:
        result["errno"], result["error"] = exc.errno, type(exc).__name__ + ": " + str(exc)
    result["finished"] = stamp()
    result["elapsed_seconds"] = round(time.monotonic() - start, 6)
    return result


def classify(result):
    if result["stop_reasons"]:
        return "STOP"
    if result["incomplete_reasons"]:
        return "PRECHECK_INCOMPLETE"
    ready = (result.get("config_valid") is True and result.get("postcheck") == "MATCH"
             and result.get("stats_before", {}).get("all_three_up") is True
             and result.get("stats_after", {}).get("all_three_up") is True
             and len(result.get("tcp", [])) == 3 and all(r["connected"] for r in result["tcp"]))
    return "PRECHECK_READY" if ready else "PRECHECK_NOT_READY"


def inspect(runner, hostname):
    result = {"status": "STOP", "scope": "LB_CURRENT_SNAPSHOT_PREFLIGHT_ONLY",
              "stage_b": "NOT_COMPLETED", "authenticated_api": "NOT_TESTED",
              "failover": "NOT_TESTED", "final_acceptance": "PENDING",
              "stop_reasons": [], "incomplete_reasons": [], "observations": []}
    before = config_before = None
    try:
        if hostname.split(".", 1)[0] != HOST:
            raise Stop("WRONG_HOST: expected " + HOST)
        before = snapshot(runner, "01_before")
        result["before"] = before
        config_before = config_state(runner, "02_before")
        result["config_before"] = config_before
        if config_before["config_hashes"].get(CONFIG) != BASELINE_CONFIG_SHA256 or len(config_before["config_hashes"]) != 1:
            result["incomplete_reasons"].append("CONFIG_DIFFERS_FROM_STAGE_A_OR_CONF_D_NOT_EMPTY_REVIEW_REQUIRED")
        version = runner.run("03_version", ["haproxy", "-v"])
        if version["return_code"] != 0 or version.get("execution_error"):
            result["incomplete_reasons"].append("VERSION_QUERY_INCOMPLETE")
        check = runner.run("04_config_check", ["haproxy", "-c", "-f", CONFIG, "-f", CFGDIR], privileged=True)
        if check.get("execution_error") or check["return_code"] in (None, 124, 137):
            result["incomplete_reasons"].append("CONFIG_CHECK_COMMAND_INCOMPLETE")
        result["config_valid"] = check["return_code"] == 0 and not check.get("execution_error")
        if check["stderr"].strip() and result["config_valid"]:
            # HAProxy versions may print a success line to stderr; accept ONLY that.
            if check["stderr"].strip() != "Configuration file is valid":
                result["incomplete_reasons"].append("CONFIG_CHECK_STDERR_REQUIRES_REVIEW")
        if not result["config_valid"]:
            result["observations"].append("CONFIG_CHECK_NOT_VALID")
            result["incomplete_reasons"].append("CONFIG_CHECK_NONZERO_REVIEW_REQUIRED")
        try:
            result["stats_before"] = query_stats(runner, "05_before")
        except Stop as exc:
            result["incomplete_reasons"].append(str(exc))
        result["tcp"] = []
        for name, ip in SERVERS.items():
            result["tcp"].append(tcp_probe(name, ip))
            write_json(runner.folder / "TCP_PROBES.json", result["tcp"])
        try:
            result["stats_after"] = query_stats(runner, "07_after")
        except Stop as exc:
            result["incomplete_reasons"].append(str(exc))
    except (Stop, OSError, ValueError) as exc:
        result["stop_reasons"].append(str(exc))
    except KeyboardInterrupt:
        result["stop_reasons"].append("OPERATOR_INTERRUPTED")
    except Exception as exc:
        result["stop_reasons"].append("COLLECTION_ERROR: " + type(exc).__name__ + ": " + str(exc))
    finally:
        if before is not None:
            try:
                result["after"] = snapshot(runner, "08_after")
                result["config_after"] = config_state(runner, "09_after")
                if result["after"] != before or result["config_after"] != config_before:
                    raise Stop("STATE_OR_CONFIG_CHANGED_DURING_CHECK")
                result["postcheck"] = "MATCH"
            except (Exception, KeyboardInterrupt) as exc:
                result["postcheck"] = "FAILED"
                result["stop_reasons"].append("POSTCHECK: " + str(exc))
    result["status"] = classify(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run the bounded LB preflight once")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        return 2
    if os.getuid() == 0 or os.geteuid() == 0:
        print("STOP: use the normal LB login account after sudo -v; do not use sudo python3.", file=sys.stderr)
        return 2
    os.umask(0o077)
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir).resolve()
    if not home.is_dir() or home.stat().st_uid != os.getuid():
        print("STOP: normal account home is unavailable or has unexpected ownership.", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_STAGEB_PREFLIGHT_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_", dir=home))
    metadata = {"kit_version": VERSION, "started": stamp(), "hostname": socket.gethostname(),
                "user": account.pw_name, "uid": os.getuid(), "home": str(home), "kernel": list(os.uname()),
                "evidence_directory": str(folder), "authorization": "User request: 권장 사항 착수; LB read-only preflight preparation",
                "historical_state_reconstructed": False, "configuration_changes_attempted": False}
    write_json(folder / "METADATA.json", metadata)
    shutil.copyfile(Path(__file__).resolve(), folder / "collector-used.py")
    try:
        binaries = tools_available()
        write_json(folder / "TOOLS.json", tool_metadata(binaries))
        result = inspect(Runner(folder, binaries), metadata["hostname"])
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "STOP", "stage_b": "NOT_COMPLETED", "final_acceptance": "PENDING",
                  "stop_reasons": [type(exc).__name__ + ": " + str(exc)]}
    result["finished"] = stamp()
    write_json(folder / "RESULT.json", result)
    try:
        archive, sidecar = package(folder)
    except Exception as exc:
        print("STOP: packaging failed; preserve evidence directory: " + str(folder), file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2
    print("STATUS=" + result["status"])
    for reason in result.get("stop_reasons", []) + result.get("incomplete_reasons", []):
        print("REASON=" + reason)
    print("EVIDENCE_DIR=" + str(folder))
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    print("Return ARCHIVE and SIDECAR, including NOT_READY or STOP results.")
    return 0 if result["status"] == "PRECHECK_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
