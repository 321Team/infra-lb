"""Mock/local only. Never invokes sudo, nft or any real remote host."""
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import collect_preflight as base
import stageb_common as common
import stageb_injector as injector
import stageb_observer as observer
import run_stageb as controller
from test_preflight import ready_csv


def inputs():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    return dict(run_id="a" * 32, source_revision="b" * 40, reviewed_revision="b" * 40,
                review_reference="TEST_ONLY", runtime_authorized=True, lead="TEST_ONLY",
                target="10.1.93.104:6443", lb_user="test_user", oob_reference="TEST_ONLY",
                window_start_kst=(now - dt.timedelta(minutes=1)).isoformat(),
                window_end_kst=(now + dt.timedelta(minutes=20)).isoformat())


class Clock:
    def __init__(self):
        self.value = 1000.0
    def monotonic(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class FakeRunner:
    def __init__(self, folder, case):
        self.folder, self.case = folder, case
        self.tools = {}
        self.present = False
        self.injected = False
        self.calls = []

    def run(self, name, args, privileged=False, input_bytes=None):
        self.calls.append((name, args, input_bytes))
        output = ""
        rc = 0
        table = injector.table_name("a" * 32)
        if args[:4] == ["nft", "-j", "list", "tables"]:
            tables = [{"table": {"family": "inet", "name": "firewalld"}}]
            if self.present:
                tables.append({"table": {"family": "inet", "name": table}})
            output = json.dumps({"nftables": tables})
        elif args[0] == "nft" and "firewalld" in args:
            output = json.dumps({"nftables": [{"chain": {"hook": "output", "prio": 10}}]})
        elif args[:4] == ["nft", "-j", "list", "table"]:
            marker = "WRONG" if self.case == "marker" else "P1-LB-01:" + "a" * 32
            output = json.dumps({"nftables": [{"table": {"name": table, "comment": marker}},
                    {"rule": {"expr": [{"counter": {"packets": 9}}]}}]})
        elif args[:3] == ["nft", "-c", "-f"]:
            rc = 2 if self.case == "syntax" else 0
        elif args[:2] == ["nft", "-f"]:
            self.present = self.injected = True
            rc = 2 if self.case == "uncertain_apply" else 0
        elif args[:3] == ["nft", "delete", "table"]:
            if self.case == "delete_fail":
                rc = 2
            else:
                self.present = False
        elif args[0] == "ip":
            output = json.dumps([{"prefsrc": base.TARGET, "dev": base.IFACE}])
        elif args[0] == "systemctl":
            output = "active\n"
        elif args[0] == "socat":
            raw = ready_csv()
            lines = raw.splitlines()
            if self.present or (self.injected and self.case == "recovery"):
                for n, line in enumerate(lines):
                    if ",k8s-control03," in line and self.case != "no_down":
                        status = "MAINT" if self.case == "maint" else "DOWN"
                        lines[n] = line.replace(",UP,", "," + status + ",").replace("L4OK", "L4TOUT")
                    if ",k8s-control02," in line and self.case == "peer_down":
                        lines[n] = line.replace(",UP,", ",DOWN,").replace("L4OK", "L4TOUT")
            output = "\n".join(lines) + "\n"
        else:
            raise AssertionError(args)
        return dict(name=name, return_code=rc, stdout=output, stderr="", outer_timeout=False)


class RuntimeFlowTests(unittest.TestCase):
    def flow(self, case="success", guard_case=None):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            common.atomic(folder / "LEASE.json", {})
            clock = Clock()
            runner = FakeRunner(folder, case)
            data = inputs()
            instance = injector.Injector(runner, folder, data)
            config = {"pid": 123, "config_hashes": {base.CONFIG: base.BASELINE_CONFIG_SHA256}}
            def guard(window):
                if guard_case == "before" or (guard_case == "during" and runner.present):
                    raise base.Stop("API_LEASE_EXPIRED_OR_INVALID")
                return {"sequence": int(clock.value)}
            with patch.object(injector.time, "monotonic", clock.monotonic), \
                 patch.object(injector.time, "sleep", clock.sleep), \
                 patch.object(injector.signal, "signal"), \
                 patch.object(base, "config_state", return_value=config), \
                 patch.object(base, "snapshot", return_value={}), \
                 patch.object(instance, "guard", side_effect=guard):
                result = instance.run()
            return result, runner

    def test_success_is_candidate_not_acceptance(self):
        result, runner = self.flow()
        self.assertEqual(result["status"], "PASS_CANDIDATE")
        self.assertTrue(result["automatic_down"])
        self.assertFalse(runner.present)
        self.assertEqual(result["stage_b"], "NOT_COMPLETED")
        self.assertEqual(result["drop_packets"], 9)

    def test_no_down_peer_down_and_maint_are_failures_with_cleanup(self):
        for case in ("no_down", "peer_down", "maint"):
            with self.subTest(case=case):
                result, runner = self.flow(case)
                self.assertEqual(result["status"], "STOP")
                self.assertFalse(runner.present)

    def test_recovery_failure_never_passes(self):
        result, runner = self.flow("recovery")
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(runner.present)
        self.assertFalse(result["final_stats"]["all_three_up"])

    def test_uncertain_apply_also_cleans_up(self):
        result, runner = self.flow("uncertain_apply")
        self.assertTrue(result["fault_attempted"])
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(runner.present)

    def test_nft_check_failure_cannot_inject(self):
        result, runner = self.flow("syntax")
        self.assertFalse(runner.injected)
        self.assertEqual(result["status"], "STOP")

    def test_lost_lease_before_and_during_fault(self):
        for case in ("before", "during"):
            with self.subTest(case=case):
                result, runner = self.flow(guard_case=case)
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(runner.injected, case == "during")
                self.assertFalse(runner.present)

    def test_delete_failure_or_foreign_marker_is_unconfirmed(self):
        for case in ("delete_fail", "marker"):
            with self.subTest(case=case):
                result, runner = self.flow(case)
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(result["cleanup"], "UNCONFIRMED")
                self.assertTrue(runner.present)
                if case == "marker":
                    self.assertFalse(any(args[:2] == ["nft", "delete"] for _, args, _ in runner.calls))


class GateTests(unittest.TestCase):
    def test_runtime_inputs_fail_closed(self):
        common.validate_inputs(inputs())
        for key, value in [("runtime_authorized", False), ("reviewed_revision", "c" * 40),
                           ("window_start_kst", ""), ("target", "10.1.93.102:6443"),
                           ("lb_user", "root"), ("oob_reference", ""), ("run_id", "../../etc")]:
            with self.subTest(key=key), self.assertRaises(base.Stop):
                data = inputs()
                data[key] = value
                common.validate_inputs(data)

    def test_lease_replay_expiry_and_wrong_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with patch.object(common.time, "monotonic", return_value=100):
                common.lease(path, "a" * 32, 1)
                with self.assertRaises(base.Stop):
                    common.lease(path, "a" * 32, 1)
            self.assertEqual(common.require_lease(path, "a" * 32, 109)["sequence"], 1)
            for run_id, now in [("a" * 32, 111), ("b" * 32, 109), ("a" * 32, 99)]:
                with self.subTest(run=run_id, now=now), self.assertRaises(base.Stop):
                    common.require_lease(path, run_id, now)

    def test_rule_scope_and_invalid_names(self):
        text = injector.rules("a" * 32).decode()
        self.assertIn('oifname "ens160" ip saddr 10.1.93.109 ip daddr @target tcp dport 6443 counter drop', text)
        self.assertIn("10.1.93.104 timeout 60s", text)
        self.assertNotIn("update", text)
        self.assertNotIn("firewalld", text)
        for run_id in ["x", "a; flush ruleset", "a" * 33]:
            with self.assertRaises(base.Stop):
                injector.rules(run_id)

    def test_existing_stageb_tables_are_not_reused(self):
        with self.assertRaises(base.Stop):
            injector.check_tables({"nftables": [{"table": {"family": "inet", "name": "firewalld"}},
                                  {"table": {"family": "inet", "name": "p1lb_old"}}]})

    def test_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(base.Stop):
            common.preserve_source(Path(tmp), {"source_hashes": {}})


class ObserverTests(unittest.TestCase):
    def test_first_api_failure_is_not_retried_or_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(observer, "binaries", return_value={}), \
                 patch.object(observer.api, "inspect", return_value={"status": "API_PRECHECK_READY"}), \
                 patch.object(observer.RuntimeRunner, "run", return_value={"name": "test", "return_code": 1, "stdout": "", "stderr": ""}) as run:
                observer.run(root, inputs())
            self.assertEqual(run.call_count, 1)
            self.assertEqual(common.read(root / "STATE.json")["status"], "STOP")
            sample = json.loads((root / "SAMPLES.jsonl").read_text())
            self.assertFalse(sample["success"])

    def test_precheck_failure_produces_no_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(observer, "binaries", return_value={}), \
                 patch.object(observer.api, "inspect", return_value={"status": "STOP", "reason": "DENIED"}), \
                 patch.object(observer.RuntimeRunner, "run") as run:
                observer.run(root, inputs())
            run.assert_not_called()
            self.assertFalse((root / "SAMPLES.jsonl").exists())


class EvidenceTests(unittest.TestCase):
    def test_zero_ansible_rc_does_not_mask_missing_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(controller.classify(Path(tmp), inputs(), 0)["status"], "STOP")

    def test_archive_manifest_coverage_and_no_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "a" * 32
            archive = root / "cp.tar.gz"
            sidecar = root / "cp.tar.gz.sha256"
            for extra in [False, True]:
                with tarfile.open(archive, "w:gz") as tar:
                    values = {"good.txt": b"good", "SHA256SUMS": (hashlib.sha256(b"good").hexdigest() + "  good.txt\n").encode()}
                    if extra:
                        values["unmanifested.txt"] = b"bad"
                    for name, value in values.items():
                        item = tarfile.TarInfo("P1_LB_STAGEB_" + run_id + "/" + name)
                        item.size = len(value)
                        tar.addfile(item, io.BytesIO(value))
                sidecar.write_text(base.sha(archive) + "  P1_LB_STAGEB_" + run_id + ".tar.gz\n")
                if extra:
                    with self.assertRaises(base.Stop):
                        controller.verify_archive(archive, sidecar, run_id)
                else:
                    self.assertEqual(controller.verify_archive(archive, sidecar, run_id)["good.txt"], b"good")


if __name__ == "__main__":
    unittest.main()
