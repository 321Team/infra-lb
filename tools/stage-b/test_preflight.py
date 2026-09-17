"""Local tests: no live LB/CP network calls, no privileged execution."""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import collect_preflight as c

FIXTURE = Path(__file__).parent / "fixtures" / "stage_a_stats.txt"


def ready_csv():
    reader = csv.DictReader(io.StringIO(FIXTURE.read_text()[2:]))
    rows = list(reader)
    for row in rows:
        if row["pxname"] == c.BACKEND:
            row["status"] = "UP"
            if row["type"] == "2":
                row["check_status"] = "L4OK"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return "# " + out.getvalue()


class StatsTests(unittest.TestCase):
    def test_original_down_is_not_ready(self):
        parsed = c.parse_stats(FIXTURE.read_text())
        self.assertFalse(parsed["all_three_up"])
        self.assertEqual({r["status"] for r in parsed["servers"].values()}, {"DOWN"})

    def test_three_up(self):
        self.assertTrue(c.parse_stats(ready_csv())["all_three_up"])

    def test_not_up_states_and_failed_checks(self):
        for replacement in ("DOWN", "MAINT", "NOLB", "UP 1/2"):
            with self.subTest(status=replacement):
                raw = ready_csv().replace(",UP,", "," + replacement + ",", 1)
                self.assertFalse(c.parse_stats(raw)["all_three_up"])
        self.assertFalse(c.parse_stats(ready_csv().replace("L4OK", "L4CON", 1))["all_three_up"])

    def test_bad_addresses_and_missing_rows(self):
        original = ready_csv()
        variants = [original.replace("10.1.93.102:6443", "10.1.93.99:6443"),
                    "\n".join(l for l in original.splitlines() if ",k8s-control02," not in l),
                    original + next(l for l in original.splitlines() if ",k8s-control01," in l) + "\n",
                    original.replace("# pxname,", "# wrong,"),
                    "Permission denied\n"]
        for raw in variants:
            with self.subTest(raw=raw[:60]), self.assertRaises(c.Stop):
                c.parse_stats(raw)

    def test_zero_weight_and_backup_cannot_pass(self):
        for field, value in (("weight", "0"), ("act", "0"), ("bck", "1")):
            reader = csv.DictReader(io.StringIO(ready_csv()[2:]))
            rows = list(reader)
            next(r for r in rows if r["svname"] == "k8s-control01")[field] = value
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            self.assertFalse(c.parse_stats("# " + out.getvalue())["all_three_up"])


class FlowTests(unittest.TestCase):
    def run_flow(self, stats=None, config=None, changed=False, check_rc=0, check_stderr="", hostname=c.HOST):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Mock(folder=Path(tmp))
            runner.run.return_value = {"return_code": check_rc, "stderr": check_stderr, "stdout": "", "name": "mock"}
            state = {"ip": c.TARGET}
            cfg = config or {"pid": 123, "argv": c.EXPECTED_ARGV, "config_hashes": {c.CONFIG: c.BASELINE_CONFIG_SHA256}}
            with patch.object(c, "snapshot", side_effect=[state, {"ip": "wrong"} if changed else state]), \
                 patch.object(c, "config_state", return_value=cfg), \
                 patch.object(c, "query_stats", side_effect=stats or [c.parse_stats(ready_csv()), c.parse_stats(ready_csv())]), \
                 patch.object(c, "tcp_probe", return_value={"connected": True}) as tcp:
                result = c.inspect(runner, hostname)
                return result, tcp.call_count

    def test_all_ready_still_not_stage_b(self):
        result, calls = self.run_flow()
        self.assertEqual(result["status"], "PRECHECK_READY")
        self.assertEqual(result["stage_b"], "NOT_COMPLETED")
        self.assertEqual(calls, 3)

    def test_wrong_host_sends_no_probe(self):
        result, calls = self.run_flow(hostname="ansible01")
        self.assertEqual((result["status"], calls), ("STOP", 0))

    def test_down_then_up_is_not_ready(self):
        result, _ = self.run_flow(stats=[c.parse_stats(FIXTURE.read_text()), c.parse_stats(ready_csv())])
        self.assertEqual(result["status"], "PRECHECK_NOT_READY")

    def test_missing_stats_is_incomplete(self):
        result, calls = self.run_flow(stats=[c.Stop("socat unavailable"), c.Stop("socat unavailable")])
        self.assertEqual(result["status"], "PRECHECK_INCOMPLETE")
        self.assertEqual(calls, 3)

    def test_changed_state_stops(self):
        result, _ = self.run_flow(changed=True)
        self.assertEqual(result["status"], "STOP")

    def test_changed_config_needs_review(self):
        result, _ = self.run_flow(config={"pid": 123, "config_hashes": {c.CONFIG: "0" * 64}})
        self.assertEqual(result["status"], "PRECHECK_INCOMPLETE")

    def test_nonzero_or_warning_not_ready(self):
        for rc, stderr in ((1, "sudo: a password is required"), (0, "[WARNING] example"), (124, "")):
            result, _ = self.run_flow(check_rc=rc, check_stderr=stderr)
            self.assertEqual(result["status"], "PRECHECK_INCOMPLETE")

    def test_failed_tcp_cannot_pass(self):
        result, _ = self.run_flow()
        result["tcp"][0] = {"connected": False}
        self.assertEqual(c.classify(result), "PRECHECK_NOT_READY")

    def test_cmdline_rejects_unreviewed_options(self):
        self.assertEqual(c.check_cmdline("\0".join(c.EXPECTED_ARGV) + "\0"), c.EXPECTED_ARGV)
        for args in (c.EXPECTED_ARGV + ["-sf", "2"], c.EXPECTED_ARGV[:-4]):
            with self.assertRaises(c.Stop):
                c.check_cmdline("\0".join(args) + "\0")

    def test_missing_socat_fails_without_command(self):
        runner = Mock(tools={})
        with self.assertRaises(c.Stop):
            c.query_stats(runner, "test")
        runner.run.assert_not_called()


class RuntimePlumbingTests(unittest.TestCase):
    def test_tcp_timeout_record_with_bound_source(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        sock.getsockname.return_value = (c.TARGET, 41000)
        sock.connect.side_effect = socket.timeout("test timeout")
        with patch.object(c.socket, "socket", return_value=sock):
            result = c.tcp_probe("k8s-control01", "10.1.93.102")
        sock.bind.assert_called_once_with((c.TARGET, 0))
        sock.settimeout.assert_called_once_with(3)
        self.assertFalse(result["connected"])
        self.assertIn("TimeoutError", result["error"])

    def test_runner_real_local_rc_bytes_and_package_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "evidence"
            folder.mkdir()
            runner = c.Runner(folder, {"python": sys.executable})
            result = runner.run("local", ["python", "-c", "import sys; sys.stdout.buffer.write(b'bytes\\x00\\n'); sys.stderr.write('error\\n'); sys.exit(7)"])
            self.assertEqual(result["return_code"], 7)
            self.assertEqual((folder / "local.stdout.txt").read_bytes(), b"bytes\x00\n")
            archive, sidecar = c.package(folder)
            self.assertEqual(sidecar.read_text().split()[0], hashlib.sha256(archive.read_bytes()).hexdigest())
            with tarfile.open(archive) as tar:
                manifest = tar.extractfile("evidence/SHA256SUMS").read().decode()
                for line in manifest.splitlines():
                    checksum, name = line.split("  ", 1)
                    self.assertEqual(checksum, hashlib.sha256(tar.extractfile("evidence/" + name).read()).hexdigest())

    def test_socket_request_is_read_only_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = {n: "/usr/bin/" + n for n in ("sudo", "env", "timeout", "socat")}
            runner = c.Runner(tmp, tools)
            def fake_valid(command, **kwargs):
                self.assertEqual(command[-5:], ["/usr/bin/socat", "-T", "3", "-", "UNIX-CONNECT:" + c.SOCKET])
                self.assertEqual(kwargs["input"], b"show stat\n")
                self.assertEqual(kwargs["timeout"], 18)
                self.assertNotIn("shell", kwargs)
                kwargs["stdout"].write(ready_csv().encode())
                return subprocess.CompletedProcess(command, 0)
            with patch.object(c.subprocess, "run", side_effect=fake_valid):
                self.assertTrue(c.query_stats(runner, "mock")["all_three_up"])

    def test_optional_binary_hash_permission_failure(self):
        with patch.object(c, "sha", side_effect=PermissionError(13, "Permission denied")):
            entry = c.tool_metadata({"sudo": sys.executable})["sudo"]
        self.assertIsNone(entry["sha256"])
        self.assertEqual(entry["hash_status"], "UNAVAILABLE_PERMISSION_DENIED")

    def test_root_is_refused_before_collection(self):
        with patch.object(c.sys, "argv", ["collector", "--run"]), patch.object(c.os, "getuid", return_value=0), \
             patch.object(c.tempfile, "mkdtemp") as mk:
            self.assertEqual(c.main(), 2)
            mk.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
