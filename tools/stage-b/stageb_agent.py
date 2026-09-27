#!/usr/bin/env python3
"""Finite remote agent, always launched as the existing ordinary login user."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

import collect_api_precheck as api
from collect_preflight import Stop
import stageb_common as common


def interrupted(signum, frame):
    raise Stop("SIGNAL_" + str(signum))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "observe", "inject", "status", "lease", "abort", "stop", "archive", "cleanup"])
    p.add_argument("--role", choices=["cp", "lb"], required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--sequence", type=int)
    args = p.parse_args()
    os.umask(0o077)
    data = common.read(args.inputs)
    if not isinstance(data.get("run_id"), str) or not __import__("re").fullmatch(r"[0-9a-f]{32}", data["run_id"]):
        raise Stop("INVALID_RUN_ID")
    if args.action in {"prepare", "observe", "inject"}:
        common.validate_inputs(data)
    folder = common.work(data, args.role, create=args.action == "prepare")
    if args.action == "prepare":
        common.preserve_source(folder, data)
        common.state(folder, "PREPARED", run_id=data["run_id"])
    elif args.action in {"observe", "inject"}:
        if (args.action == "observe") != (args.role == "cp"):
            raise Stop("ROLE_ACTION_MISMATCH")
        if common.read(folder / "STATE.json")["status"] != "PREPARED":
            raise Stop("RUN_DIRECTORY_NOT_FRESH")
        for name in common.source_files():
            if common.sha(Path(__file__).resolve().parent / name) != data["source_hashes"][name]:
                raise Stop("SOURCE_CHANGED_AFTER_PREPARATION")
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGHUP, interrupted)
        fd = common.lock(folder / "PROCESS.lock")
        try:
            if args.role == "cp":
                import stageb_observer
                stageb_observer.run(folder, data)
            else:
                import stageb_injector
                stageb_injector.run(folder, data)
        except BaseException as exc:
            common.state(folder, "STOP", reason=type(exc).__name__ + ": " + str(exc))
        finally:
            os.close(fd)
    elif args.action == "lease":
        if args.role != "lb":
            raise Stop("LEASE_IS_LB_ONLY")
        common.lease(folder, data["run_id"], args.sequence)
    elif args.action == "abort":
        common.atomic(folder / "ABORT", {"at": common.stamp()})
    elif args.action == "stop":
        if args.role != "cp":
            raise Stop("USE_ABORT_FOR_LB")
        common.atomic(folder / "STOP", {"at": common.stamp()})
    elif args.action == "cleanup":
        if args.role != "lb":
            raise Stop("CLEANUP_IS_LB_ONLY")
        common.atomic(folder / "ABORT", {"at": common.stamp()})
        # A live process owns cleanup; do not race it.
        fd = common.lock(folder / "PROCESS.lock")
        try:
            import stageb_injector
            r = common.RuntimeRunner(folder, common.binaries(["sudo", "nft"]),
                                     helper_sha=data["source_hashes"]["stageb_privileged_helper.py"],
                                     policy_sha=data["source_hashes"]["stageb_privilege.sudoers"],
                                     require_helper=True)
            instance = stageb_injector.Injector(r, folder, data)
            instance.counter = int(time.time())
            instance.attempted = True
            instance.cleanup()
        finally:
            os.close(fd)
    elif args.action == "archive":
        fd = common.lock(folder / "PROCESS.lock")
        try:
            if common.read(folder / "STATE.json")["status"] not in common.TERMINAL:
                raise Stop("PROCESS_NOT_TERMINAL")
            archive, sidecar = api.package(folder)
            print(json.dumps({"archive": str(archive), "sidecar": str(sidecar)}))
            return 0
        finally:
            os.close(fd)
    print(json.dumps(common.status(folder)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("STOP: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(2)
