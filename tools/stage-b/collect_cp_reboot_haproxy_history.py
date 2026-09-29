#!/usr/bin/env python3
"""Read-only collection of HAProxy history around the 2026-09-27 CP3 reboot.

This tool does not reboot hosts, change HAProxy, firewalld, nftables, SELinux,
or Kubernetes. It only reads the HAProxy journal for a fixed historical window
and captures current service/listener/stats state as context.
"""
from __future__ import annotations

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

VERSION = "1.2"
EXPECTED_HOST = "k8s-api-lb01"
EXPECTED_USER = "server01_k8s-api-lb"
WINDOW_SINCE_UTC = "2026-09-27 08:33:00 UTC"   # 17:33 KST
WINDOW_UNTIL_UTC = "2026-09-27 08:46:30 UTC"   # 17:46:30 KST
TARGET_BACKEND = "k8s-control03"
TARGET_ADDR = "10.1.93.104:6443"
TRUSTED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
HEALTH_RE = re.compile(
    r"(?i)(?:Server\s+)?(?:\S+/)?k8s-control03.*?\b(DOWN|UP)\b"
)
ISO_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))"
)


class Stop(RuntimeError):
    pass


def now():
    t = dt.datetime.now(dt.timezone.utc)
    return {"utc": t.isoformat(), "kst": t.astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat()}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def run(folder: Path, name: str, argv: list[str], privileged: bool = False, timeout: int = 20):
    if privileged:
        argv = ["/usr/bin/sudo", "-n", "--", "/usr/bin/env", "-i",
                "PATH=" + TRUSTED_PATH, "LC_ALL=C", "LANG=C"] + argv
    started = now()
    proc = subprocess.run(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False
    )
    finished = now()
    (folder / f"{name}.stdout.txt").write_bytes(proc.stdout)
    (folder / f"{name}.stderr.txt").write_bytes(proc.stderr)
    return {
        "name": name,
        "argv": argv,
        "privileged": privileged,
        "return_code": proc.returncode,
        "started": started,
        "finished": finished,
        "stdout_file": f"{name}.stdout.txt",
        "stderr_file": f"{name}.stderr.txt",
    }


def parse_iso(token: str):
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    return dt.datetime.fromisoformat(token)


def extract_transitions(text: str):
    rows = []
    for line in text.splitlines():
        m = HEALTH_RE.search(line)
        if not m:
            continue
        ts_m = ISO_TS_RE.match(line)
        row = {"state": m.group(1).upper(), "line": line}
        if ts_m:
            row["timestamp"] = ts_m.group("ts")
        rows.append(row)
    return rows


def summarize(transitions):
    down = next((r for r in transitions if r["state"] == "DOWN" and "timestamp" in r), None)
    up = None
    if down:
        idx = transitions.index(down)
        up = next((r for r in transitions[idx + 1:] if r["state"] == "UP" and "timestamp" in r), None)
    result = {
        "target_backend": TARGET_BACKEND,
        "target_address": TARGET_ADDR,
        "transitions_found": len(transitions),
        "first_down": down,
        "first_up_after_down": up,
        "down_to_up_seconds": None,
        "historical_window_verdict": "INSUFFICIENT_NO_DOWN_UP_PAIR",
    }
    if down and up:
        delta = (parse_iso(up["timestamp"]) - parse_iso(down["timestamp"])).total_seconds()
        result["down_to_up_seconds"] = delta
        result["historical_window_verdict"] = "DOWN_UP_PAIR_FOUND"
    return result


def current_stats():
    path = Path("/var/lib/haproxy/stats")
    if not path.exists():
        return None, "STATS_SOCKET_MISSING"
    import socket as pysocket
    s = pysocket.socket(pysocket.AF_UNIX, pysocket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(str(path))
        s.sendall(b"show stat\n")
        parts = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            parts.append(chunk)
        return b"".join(parts), None
    except (OSError, TimeoutError) as exc:
        return None, type(exc).__name__ + ": " + str(exc)
    finally:
        s.close()


def package(folder: Path):
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (folder / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files))
    archive = folder.with_name(folder.name + ".tar.gz")
    with tarfile.open(archive, "x:gz") as tar:
        for p in files + [folder / "SHA256SUMS"]:
            tar.add(p, arcname=folder.name + "/" + p.name, recursive=False)
    sidecar = archive.with_name(archive.name + ".sha256")
    sidecar.write_text(f"{sha(archive)}  {archive.name}\n")
    return archive, sidecar


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    args = p.parse_args()
    if not args.run:
        raise Stop("MISSING_RUN_FLAG")
    if os.getuid() == 0 or os.getuid() != os.geteuid():
        raise Stop("RUN_AS_NORMAL_ACCOUNT_ONLY")
    host = socket.gethostname().split(".", 1)[0]
    user = pwd.getpwuid(os.getuid()).pw_name
    if (host, user) != (EXPECTED_HOST, EXPECTED_USER):
        raise Stop(f"WRONG_HOST_OR_USER: {host}/{user}")
    for tool in ("/usr/bin/journalctl", "/usr/bin/systemctl", "/usr/sbin/ss", "/usr/bin/sudo"):
        if not Path(tool).exists():
            raise Stop("MISSING_TOOL: " + tool)

    home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    if not home.is_dir() or home.stat().st_uid != os.getuid():
        raise Stop("HOME_OWNERSHIP_MISMATCH")
    os.umask(0o077)
    folder = Path(tempfile.mkdtemp(
        prefix="FDS_P1_LB_01_CP_REBOOT_HISTORY_"
               + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_",
        dir=home,
    ))
    shutil.copyfile(Path(__file__).resolve(), folder / Path(__file__).name)
    records = []
    result = {
        "version": VERSION,
        "scope": "READ_ONLY_HISTORICAL_COLLECTION",
        "configuration_changes_attempted": False,
        "reboot_attempted": False,
        "fault_injection_attempted": False,
        "historical_window": {"since_utc": WINDOW_SINCE_UTC, "until_utc": WINDOW_UNTIL_UTC},
        "target_backend": TARGET_BACKEND,
        "target_address": TARGET_ADDR,
        "started": now(),
        "errors": [],
    }

    try:
        records.append(run(folder, "01_haproxy_active",
                           ["/usr/bin/systemctl", "is-active", "haproxy.service"]))
        records.append(run(folder, "02_listener",
                           ["/usr/sbin/ss", "-H", "-lnt", "sport", "=", ":6443"]))
        journal_filters = [
            ("10_journal_unit", ["/usr/bin/journalctl", "--no-pager", "--utc",
                                 "-o", "short-iso-precise", "--since", WINDOW_SINCE_UTC,
                                 "--until", WINDOW_UNTIL_UTC, "-u", "haproxy.service"]),
            ("11_journal_identifier", ["/usr/bin/journalctl", "--no-pager", "--utc",
                                       "-o", "short-iso-precise", "--since", WINDOW_SINCE_UTC,
                                       "--until", WINDOW_UNTIL_UTC, "SYSLOG_IDENTIFIER=haproxy"]),
            ("12_journal_comm", ["/usr/bin/journalctl", "--no-pager", "--utc",
                                 "-o", "short-iso-precise", "--since", WINDOW_SINCE_UTC,
                                 "--until", WINDOW_UNTIL_UTC, "_COMM=haproxy"]),
        ]
        all_text = []
        for name, argv in journal_filters:
            rec = run(folder, name, argv, privileged=True, timeout=30)
            records.append(rec)
            if rec["return_code"] == 0:
                all_text.append((folder / rec["stdout_file"]).read_text(errors="replace"))
            else:
                result["errors"].append(name + f": rc={rec['return_code']}")
        transitions = extract_transitions("\n".join(all_text))
        result["haproxy_transition_summary"] = summarize(transitions)
        write_json(folder / "TRANSITIONS.json", transitions)

        stats, stats_error = current_stats()
        if stats is not None:
            (folder / "20_current_stats.stdout.txt").write_bytes(stats)
            result["current_stats"] = "COLLECTED_CONTEXT_ONLY"
        else:
            (folder / "20_current_stats.stderr.txt").write_text((stats_error or "UNKNOWN") + "\n")
            result["current_stats"] = "UNAVAILABLE: " + (stats_error or "UNKNOWN")

        # Historical logs can explain HAProxy state transitions but cannot recreate
        # continuous API samples that were never collected.
        if result["haproxy_transition_summary"]["historical_window_verdict"] == "DOWN_UP_PAIR_FOUND":
            result["verdict"] = "HISTORICAL_HAPROXY_TRANSITION_FOUND_API_BUDGET_STILL_NOT_PROVEN"
        else:
            result["verdict"] = "HISTORICAL_HAPROXY_TRANSITION_NOT_PROVEN"
    except (Exception, KeyboardInterrupt) as exc:
        result["errors"].append(type(exc).__name__ + ": " + str(exc))
        result["verdict"] = "STOP"
    result["records"] = records
    result["finished"] = now()
    write_json(folder / "RESULT.json", result)
    archive, sidecar = package(folder)
    print("VERDICT=" + result["verdict"])
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    return 0 if result["verdict"] != "STOP" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("STOP: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(2)
