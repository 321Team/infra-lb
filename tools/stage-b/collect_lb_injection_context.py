#!/usr/bin/env python3
"""Collect LB preflight plus firewall context once. No rule changes or injection."""
import argparse
import datetime as dt
import os
from pathlib import Path
import pwd
import shutil
import socket
import sys
import tempfile

import collect_preflight as base

VERSION = "1.1"


def collect(runner, hostname):
    result = {"status": "STOP", "scope": "LB_READ_ONLY_PREPARATION",
              "injection": "NOT_RUN", "injection_ready": "NOT_EVALUATED",
              "stage_b": "NOT_COMPLETED", "context_errors": []}
    if hostname.split(".", 1)[0] != base.HOST:
        result["context_errors"].append("WRONG_HOST")
        return result
    preflight = base.inspect(runner, hostname)
    result["lb_preflight"] = preflight
    if preflight["status"] == "STOP":
        result["context_errors"].append("LB_PREFLIGHT_STOP; firewall queries skipped")
        return result

    def read(name, args, privileged=False, as_json=False):
        try:
            if args[0] not in runner.tools:
                raise base.Stop("MISSING_TOOL: " + args[0])
            record = runner.run(name, args, privileged=privileged)
            return base.json_output(record) if as_json else base.require_ok(record).strip()
        except (base.Stop, ValueError, OSError, TypeError) as exc:
            result["context_errors"].append(name + ": " + str(exc))
            return None

    try:
        result["boot_id"] = read("10_boot_id", ["cat", "/proc/sys/kernel/random/boot_id"])
        result["service_units"] = read("11_firewall_units", ["systemctl", "show", "firewalld.service", "nftables.service",
            "--property=Id,LoadState,ActiveState,SubState,UnitFileState"])
        result["routes"] = {}
        for i, address in enumerate(base.SERVERS.values()):
            route = read("12_route_" + str(i + 1), ["ip", "-j", "-4", "route", "get", address], as_json=True)
            result["routes"][address] = route
            if route is not None and (not isinstance(route, list) or len(route) != 1 or
                    route[0].get("prefsrc") != base.TARGET or route[0].get("dst") != address):
                result["context_errors"].append("UNEXPECTED_LB_ROUTE: " + address)
        result["nft_version"] = read("13_nft_version", ["nft", "--version"])
        rules = read("14_nft_ruleset", ["nft", "-j", "-a", "list", "ruleset"], privileged=True, as_json=True)
        if rules is not None and (not isinstance(rules, dict) or not isinstance(rules.get("nftables"), list)):
            result["context_errors"].append("INVALID_NFT_JSON_SCHEMA")
        # Raw rules remain in stdout. They are observations, never restore/apply input.
        result["firewalld_version"] = read("15_firewalld_version", ["firewall-cmd", "--version"])
        result["firewalld_state"] = read("16_firewalld_state", ["firewall-cmd", "--state"], privileged=True)
        if result["firewalld_state"] == "running":
            read("17_firewalld_active_zones", ["firewall-cmd", "--get-active-zones"], privileged=True)
            read("18_firewalld_runtime", ["firewall-cmd", "--list-all-zones"], privileged=True)
            read("19_firewalld_permanent", ["firewall-cmd", "--permanent", "--list-all-zones"], privileged=True)
        else:
            result["context_errors"].append("FIREWALLD_NOT_RUNNING_OR_UNCONFIRMED; no start attempted")
        result["services_after"] = read("20_firewall_units_after", ["systemctl", "show", "firewalld.service", "nftables.service",
            "--property=Id,LoadState,ActiveState,SubState,UnitFileState"])
        if result["services_after"] != result["service_units"]:
            result["context_errors"].append("FIREWALL_UNIT_STATE_CHANGED")
        result["status"] = ("PREPARATION_DATA_COLLECTED" if not result["context_errors"]
            and preflight["status"] == "PRECHECK_READY" else "PREPARATION_INCOMPLETE")
    except (Exception, KeyboardInterrupt) as exc:
        result["context_errors"].append(type(exc).__name__ + ": " + str(exc))
        result["status"] = "STOP"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run or os.getuid() == 0 or os.geteuid() == 0:
        print("STOP: use normal LB login account after sudo -v; do not use sudo python3.", file=sys.stderr)
        return 2
    os.umask(0o077)
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir).resolve()
    if not home.is_dir() or home.stat().st_uid != os.getuid():
        print("STOP: normal account home unavailable or ownership mismatch.", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_INJECTION_CONTEXT_" +
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_", dir=home))
    base.write_json(folder / "METADATA.json", {"version": VERSION, "started": base.stamp(),
        "hostname": socket.gethostname(), "account": account.pw_name, "uid": os.getuid(),
        "collector_sha256": base.sha(Path(__file__).resolve()),
        "helper_sha256": base.sha(Path(base.__file__).resolve()),
        "configuration_changes_attempted": False, "injection_host_constraint": base.HOST,
        "source_commit_mapping": "SOURCE.json in delivered kit; source copies/hashes included here"})
    try:
        shutil.copyfile(Path(__file__).resolve(), folder / "collect_lb_injection_context.py")
        shutil.copyfile(Path(base.__file__).resolve(), folder / "collect_preflight.py")
        binaries = base.tools_available()
        for name in ("nft", "firewall-cmd"):
            found = shutil.which(name, path=base.TRUSTED_PATH)
            if found:
                binaries[name] = str(Path(found).resolve())
        base.write_json(folder / "TOOLS.json", base.tool_metadata(binaries))
        result = collect(base.Runner(folder, binaries), socket.gethostname())
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "STOP", "context_errors": [type(exc).__name__ + ": " + str(exc)],
                  "injection": "NOT_RUN", "stage_b": "NOT_COMPLETED"}
    result["finished"] = base.stamp()
    base.write_json(folder / "RESULT.json", result)
    try:
        archive, sidecar = base.package(folder)
    except Exception as exc:
        print("STOP: package failed; preserve " + str(folder) + ": " + str(exc), file=sys.stderr)
        return 2
    print("STATUS=" + result["status"])
    for error in result.get("context_errors", []):
        print("REASON=" + error)
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    return 0 if result["status"] == "PREPARATION_DATA_COLLECTED" else 2


if __name__ == "__main__":
    sys.exit(main())
