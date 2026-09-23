"""LB-only bounded one-destination fault. Runtime code, independent review required."""
import datetime as dt
import json
import os
import re
import signal
import time

import collect_preflight as lb
from collect_preflight import Stop, json_output, require_ok
from stageb_common import (RuntimeRunner, atomic, binaries, lock, read, require_lease,
                          state, validate_inputs)

PREFIX = "p1lb_"
BASELINE_SECONDS = 30
FAULT_SECONDS = 60
RECOVERY_SECONDS = 30


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


def check_tables(data, allowed=None):
    tables = [x["table"] for x in data.get("nftables", []) if "table" in x]
    if not any(t.get("family") == "inet" and t.get("name") == "firewalld" for t in tables):
        raise Stop("EXPECTED_FIREWALLD_TABLE_MISSING")
    if any(t.get("name", "").startswith(PREFIX) and t["name"] != allowed for t in tables):
        raise Stop("OTHER_STAGEB_TABLE_EXISTS")
    return tables


def healthy_peers(stats):
    if stats["backend_status"] != "UP":
        raise Stop("AGGREGATE_BACKEND_NOT_UP")
    for name, row in stats["servers"].items():
        if row["act"] != "1" or row["bck"] != "0" or int(row["weight"]) <= 0:
            raise Stop("BACKEND_ADMIN_STATE_CHANGED")
        if name != "k8s-control03" and (row["status"], row["check_status"]) != ("UP", "L4OK"):
            raise Stop("OTHER_BACKEND_NOT_HEALTHY")
        if name == "k8s-control03" and row["status"] != "UP" and not re.fullmatch(r"(?:UP|DOWN)(?: [0-9]+/[0-9]+)?", row["status"]):
            raise Stop("TARGET_ADMIN_OR_UNEXPECTED_STATE")


def down_observed(stats):
    row = stats["servers"]["k8s-control03"]
    return row["status"] == "DOWN" and row["check_status"] in {"L4TOUT", "L4CON"}


class Injector:
    def __init__(self, runner, folder, data):
        self.r, self.folder, self.data = runner, folder, data
        self.name = table_name(data["run_id"])
        self.counter = 0
        self.armed = False
        self.attempted = False
        self.cleaned = False
        self.down = False
        self.drop_packets = 0

    def command(self, suffix, args, privileged=True, input_bytes=None):
        self.counter += 1
        return self.r.run("runtime_%04d_%s" % (self.counter, suffix), args, privileged, input_bytes)

    def tables(self):
        return json_output(self.command("tables", ["nft", "-j", "list", "tables"]))

    def cleanup(self):
        """Only this run's marked table; no broad flush or firewalld modification."""
        if not self.attempted:
            self.cleaned = True
            return
        tables = self.tables()
        present = any(x.get("table", {}).get("family") == "inet" and
                      x["table"].get("name") == self.name for x in tables.get("nftables", []))
        if present:
            own = json_output(self.command("own_before_delete", ["nft", "-j", "list", "table", "inet", self.name]))
            entries = [x["table"] for x in own.get("nftables", []) if "table" in x]
            if len(entries) != 1 or entries[0].get("comment") != "P1-LB-01:" + self.data["run_id"]:
                raise Stop("REFUSE_DELETE_TABLE_WITHOUT_MATCHING_RUN_MARKER")
            for obj in own.get("nftables", []):
                for expr in obj.get("rule", {}).get("expr", []):
                    if "counter" in expr:
                        self.drop_packets += expr["counter"].get("packets", 0)
            require_ok(self.command("delete_own_table", ["nft", "delete", "table", "inet", self.name]))
        remaining = self.tables()
        if any(x.get("table", {}).get("name") == self.name for x in remaining.get("nftables", [])):
            raise Stop("OWN_TABLE_STILL_PRESENT")
        self.cleaned = True

    def guard(self, window_end):
        if (self.folder / "ABORT").exists():
            raise Stop("CONTROLLER_OR_OPERATOR_ABORT")
        if dt.datetime.now(dt.timezone.utc) >= window_end:
            raise Stop("WORK_WINDOW_ENDED")
        return require_lease(self.folder, self.data["run_id"])

    def stats(self):
        return lb.parse_stats(require_ok(self.command("stats", ["socat", "-T", "1", "-", "UNIX-CONNECT:" + lb.SOCKET], input_bytes=b"show stat\n")))

    def run(self):
        result = {"status": "STOP", "fault_attempted": False, "automatic_down": False,
                  "cleanup": "NOT_NEEDED", "stage_b": "NOT_COMPLETED", "final_acceptance": "PENDING"}
        original = firewall = None
        try:
            window_end = validate_inputs(self.data)
            original = lb.config_state(self.r, "initial")
            if original["config_hashes"] != {lb.CONFIG: lb.BASELINE_CONFIG_SHA256}:
                raise Stop("HAPROXY_CONFIG_DIFFERS_FROM_CONFIRMED_BASELINE")
            lb.snapshot(self.r, "initial")
            route = json_output(self.command("route", ["ip", "-j", "-4", "route", "get", "10.1.93.104"], False))
            if len(route) != 1 or route[0].get("prefsrc") != lb.TARGET or route[0].get("dev") != lb.IFACE:
                raise Stop("LB_TARGET_ROUTE_CHANGED")
            require_ok(self.command("firewalld", ["systemctl", "is-active", "firewalld.service"], False))
            check_tables(self.tables())
            firewall = json_output(self.command("firewalld_rules", ["nft", "-s", "-j", "list", "table", "inet", "firewalld"]))
            chains = [x["chain"] for x in firewall.get("nftables", []) if "chain" in x]
            if not any(c.get("hook") == "output" and c.get("prio") == 10 for c in chains):
                raise Stop("FIREWALLD_OUTPUT_PRIORITY_DIFFERS")
            require_ok(self.command("nft_check", ["nft", "-c", "-f", "-"], input_bytes=rules(self.data["run_id"])))
            start = time.monotonic()
            first = None
            while first is None or time.monotonic() - first < BASELINE_SECONDS:
                if time.monotonic() - start > 60:
                    raise Stop("BASELINE_OR_FIRST_LEASE_TIMEOUT")
                if not (self.folder / "LEASE.json").exists():
                    time.sleep(0.2)
                    continue
                observed = self.guard(window_end)
                stats = self.stats()
                if not stats["all_three_up"]:
                    raise Stop("BASELINE_NOT_THREE_UP_L4OK")
                first = time.monotonic() if first is None else first
                state(self.folder, "BASELINE", stats=stats, observer_sequence=observed["sequence"])
                time.sleep(1)
            # Recheck after the last potentially blocking query, before mutation.
            observed = self.guard(window_end)
            if (window_end - dt.datetime.now(dt.timezone.utc)).total_seconds() < 150:
                raise Stop("INSUFFICIENT_WINDOW_FOR_FAULT_AND_RECOVERY")
            self.attempted = True  # Set before command: uncertain commit must also be cleaned.
            require_ok(self.command("inject", ["nft", "-f", "-"], input_bytes=rules(self.data["run_id"])))
            self.armed = True
            injected = time.monotonic()
            state(self.folder, "INJECTED", table=self.name, kernel_timeout_seconds=60,
                  observer_sequence=observed["sequence"])
            # End at 55 seconds so cleanup normally precedes the independent kernel expiry.
            while time.monotonic() - injected < FAULT_SECONDS - 5:
                observed = self.guard(window_end)
                stats = self.stats()
                healthy_peers(stats)
                self.down = self.down or down_observed(stats)
                state(self.folder, "FAULT", stats=stats, automatic_down=self.down, observer_sequence=observed["sequence"])
                time.sleep(1)
            self.cleanup()
            recovered = None
            started = time.monotonic()
            while recovered is None or time.monotonic() - recovered < RECOVERY_SECONDS:
                if time.monotonic() - started > 65:
                    raise Stop("RECOVERY_NOT_STABLE_FOR_30_SECONDS")
                observed = self.guard(window_end)
                stats = self.stats()
                healthy_peers(stats)
                recovered = (time.monotonic() if recovered is None else recovered) if stats["all_three_up"] else None
                state(self.folder, "RECOVERY", stats=stats, observer_sequence=observed["sequence"])
                time.sleep(1)
            if not self.down or self.drop_packets <= 0:
                raise Stop("AUTOMATIC_DOWN_OR_DROP_COUNTER_NOT_OBSERVED")
            result["status"] = "PASS_CANDIDATE"
        except BaseException as exc:
            result["reason"] = type(exc).__name__ + ": " + str(exc)
        finally:
            # A second terminal disconnect must not interrupt best-effort cleanup.
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                signal.signal(sig, signal.SIG_IGN)
            try:
                self.cleanup()
                result["cleanup"] = "OWN_TABLE_ABSENT" if self.attempted else "NO_MUTATION_ATTEMPTED"
            except BaseException as exc:
                result.update(status="STOP", cleanup="UNCONFIRMED", cleanup_error=str(exc))
            # Never omit recovery evidence on STOP. Kernel expiry alone is not cleanup PASS.
            try:
                recovery_deadline = time.monotonic() + 40
                while True:
                    result["final_stats"] = self.stats()
                    if result["final_stats"]["all_three_up"] or time.monotonic() >= recovery_deadline:
                        break
                    time.sleep(1)
                if not result["final_stats"]["all_three_up"]:
                    result["status"] = "STOP"
                if original is not None and lb.config_state(self.r, "final") != original:
                    raise Stop("HAPROXY_CONFIG_OR_PID_CHANGED")
                if firewall is not None and json_output(self.command("final_firewalld", ["nft", "-s", "-j", "list", "table", "inet", "firewalld"])) != firewall:
                    raise Stop("FIREWALLD_RULES_CHANGED")
            except BaseException as exc:
                result.update(status="STOP", postcheck_error=str(exc))
            result.update(fault_attempted=self.attempted, automatic_down=self.down,
                          drop_packets=self.drop_packets, table=self.name)
            atomic(self.folder / "RESULT.json", result)
            state(self.folder, result["status"], result=result)
        return result


def run(folder, data):
    fd = lock(folder.parent / ".p1lb-stageb-runtime.lock")
    try:
        r = RuntimeRunner(folder, binaries(["ip", "ss", "systemctl", "cat", "sha256sum", "find",
                                          "nft", "socat", "sudo", "env", "timeout"]))
        return Injector(r, folder, data).run()
    finally:
        os.close(fd)
