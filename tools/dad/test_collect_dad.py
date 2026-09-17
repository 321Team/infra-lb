"""MOCK only: imports collector but never runs system/network commands."""
import copy
from contextlib import ExitStack, redirect_stdout
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import collect_dad as c


def arp(dst, src, sent, received):
    reply = "Unicast reply from %s [00:11:22:33:44:55]  0.100ms\n" % dst if received else ""
    return ("ARPING %s from %s ens160\n%sSent %s probes (%s broadcast(s))\nReceived %s response(s)\n"
            % (dst, src, reply, sent, sent, received))


class FakeRunner:
    def __init__(self, changes=None):
        self.calls = []
        self.changes = changes or {}

    def run(self, name, args, privileged=False):
        self.calls.append((name, args, privileged))
        if name.endswith("ip_address"):
            out = json.dumps([{"ifname": c.IFACE, "addr_info": [{"family": "inet", "scope": "global",
                              "local": c.TARGET, "prefixlen": 24}]}])
        elif name.endswith("ip_link"):
            out = json.dumps([{"ifname": c.IFACE, "flags": ["UP", "LOWER_UP", "BROADCAST"],
                              "operstate": "UP", "link_type": "ether", "address": "00:50:56:11:22:33"}])
        elif name.endswith("haproxy"):
            out = "active\n"
        elif name.endswith("listeners"):
            out = "LISTEN 0 4096 10.1.93.109:6443 0.0.0.0:*\n"
        elif name == "01_arping_version":
            out = "arping from iputils 20240905\n"
        elif name == "03_peer_route":
            out = json.dumps([{"dst": c.PEER, "dev": c.IFACE, "prefsrc": c.TARGET}])
        elif name == "04_l2_peer":
            out = arp(c.PEER, c.TARGET, 1, 1)
        elif name == "05_dad":
            out = arp(c.TARGET, "0.0.0.0", 3, 0)
        else:
            raise AssertionError("Unexpected command: " + name)
        record = {"name": name, "stdout": out, "stderr": "", "return_code": 0, "outer_timeout": False}
        record.update(copy.deepcopy(self.changes.get(name, {})))
        return record


class CollectorTests(unittest.TestCase):
    def run_case(self, changes=None, hostname=c.HOST):
        runner = FakeRunner(changes)
        with patch.object(c.subprocess, "run", side_effect=AssertionError("MOCK must never execute")):
            result = c.inspect(runner, hostname)
        self.assertLessEqual(sum(x[0] == "05_dad" for x in runner.calls), 1)
        return result, runner

    def test_current_pass_is_not_final_acceptance(self):
        result, runner = self.run_case()
        self.assertEqual(result["status"], "PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED")
        self.assertEqual(result["final_acceptance"], "PENDING_REVIEW")
        self.assertFalse(result["historical_original_recovered"])
        self.assertEqual(result["postcheck"], "MATCH")
        dad = next(call for call in runner.calls if call[0] == "05_dad")
        self.assertEqual(dad[1], ["arping", "-D", "-c", "3", "-I", "ens160", "10.1.93.109"])

    def test_wrong_host_runs_no_commands(self):
        result, runner = self.run_case(hostname="ansible01")
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(runner.calls)

    def test_sudo_failure_prevents_packets(self):
        result, runner = self.run_case({"01_arping_version": {"return_code": 1, "stderr": "sudo: a password is required\n"}})
        self.assertFalse(result["dad_attempted"])
        self.assertFalse(any("l2_peer" in x[0] for x in runner.calls))

    def test_wrong_address_prevents_dad(self):
        bad = json.dumps([{"ifname": c.IFACE, "addr_info": [{"family": "inet", "scope": "global", "local": "10.1.93.108", "prefixlen": 24}]}])
        result, _ = self.run_case({"02_before_ip_address": {"stdout": bad}})
        self.assertFalse(result["dad_attempted"])

    def test_link_down_prevents_dad(self):
        bad = json.dumps([{"ifname": c.IFACE, "flags": ["BROADCAST"], "operstate": "DOWN", "link_type": "ether", "address": "00:50:56:11:22:33"}])
        result, _ = self.run_case({"02_before_ip_link": {"stdout": bad}})
        self.assertFalse(result["dad_attempted"])

    def test_routed_peer_is_rejected(self):
        route = json.dumps([{"dev": c.IFACE, "prefsrc": c.TARGET, "gateway": "10.1.93.1"}])
        result, _ = self.run_case({"03_peer_route": {"stdout": route}})
        self.assertFalse(result["dad_attempted"])

    def test_no_peer_reply_prevents_dad_and_keeps_postcheck(self):
        result, runner = self.run_case({"04_l2_peer": {"stdout": arp(c.PEER, c.TARGET, 1, 0), "return_code": 1}})
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(result["dad_attempted"])
        self.assertTrue(any(x[0] == "06_after_haproxy" for x in runner.calls))

    def test_conflict_does_not_retry_or_pass(self):
        result, _ = self.run_case({"05_dad": {"stdout": arp(c.TARGET, "0.0.0.0", 1, 1), "return_code": 1}})
        self.assertEqual(result["status"], "FAIL_CONFLICT_SUSPECTED_REVIEW_REQUIRED")
        self.assertEqual(result["dad"]["reply_macs"], ["00:11:22:33:44:55"])
        self.assertEqual(result["postcheck"], "MATCH")

    def test_duplicate_even_with_zero_rc_cannot_pass(self):
        result, _ = self.run_case({"05_dad": {"stdout": arp(c.TARGET, "0.0.0.0", 3, 1)}})
        self.assertNotEqual(result["status"], "PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED")

    def test_timeout_cannot_pass_with_pass_looking_output(self):
        for change in ({"return_code": 124}, {"return_code": None, "outer_timeout": True}):
            with self.subTest(change=change):
                result, _ = self.run_case({"05_dad": change})
                self.assertEqual(result["status"], "STOP")
                self.assertIsNone(result["dad"]["arping_return_code"])

    def test_partial_send_cannot_pass(self):
        result, _ = self.run_case({"05_dad": {"stdout": arp(c.TARGET, "0.0.0.0", 2, 0)}})
        self.assertEqual(result["status"], "STOP")

    def test_missing_or_localized_output_cannot_pass(self):
        for output in ("", "응답 0개 수신함\n", "Received 0 response(s)\n"):
            with self.subTest(output=output):
                result, _ = self.run_case({"05_dad": {"stdout": output}})
                self.assertEqual(result["status"], "STOP")

    def test_stderr_cannot_be_masked(self):
        result, _ = self.run_case({"05_dad": {"stderr": "send: Network is down\n"}})
        self.assertEqual(result["status"], "STOP")

    def test_wrong_header_cannot_pass(self):
        result, _ = self.run_case({"05_dad": {"stdout": arp("10.1.93.108", "0.0.0.0", 3, 0)}})
        self.assertEqual(result["status"], "STOP")

    def test_reply_line_disagrees_with_zero_summary(self):
        out = arp(c.TARGET, "0.0.0.0", 3, 0) + "Unicast reply from 10.1.93.109 [00:11:22:33:44:55]\n"
        result, _ = self.run_case({"05_dad": {"stdout": out}})
        self.assertEqual(result["status"], "STOP")

    def test_interrupt_does_not_invent_rc(self):
        with tempfile.TemporaryDirectory() as d:
            runner = c.Runner(d, {"ip": "/usr/sbin/ip"})
            with patch.object(c.subprocess, "run", side_effect=KeyboardInterrupt):
                record = runner.run("interrupt", ["ip", "-j", "link"])
            self.assertIsNone(record["return_code"])
            self.assertIn("interrupted", record["execution_error"])
            self.assertTrue(Path(d, "COMMANDS.json").is_file())

    def test_post_service_failure_invalidates_pass(self):
        result, _ = self.run_case({"06_after_haproxy": {"stdout": "inactive\n", "return_code": 3}})
        self.assertEqual(result["status"], "STOP")
        self.assertEqual(result["dad"]["arping_return_code"], 0)

    def test_post_mac_change_invalidates_pass(self):
        bad = json.dumps([{"ifname": c.IFACE, "flags": ["UP", "LOWER_UP", "BROADCAST"], "operstate": "UP",
                          "link_type": "ether", "address": "00:50:56:99:22:33"}])
        result, _ = self.run_case({"06_after_ip_link": {"stdout": bad}})
        self.assertEqual(result["status"], "STOP")

    def test_raw_stdout_stderr_and_rc_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            runner = c.Runner(d, {"arping": "/usr/sbin/arping", "sudo": "/usr/bin/sudo", "env": "/usr/bin/env", "timeout": "/usr/bin/timeout"})
            def fake_run(argv, **kwargs):
                self.assertEqual(argv[:3], ["/usr/bin/sudo", "-n", "--"])
                self.assertIn("10s", argv)
                kwargs["stdout"].write(b"RAW\r\n")
                kwargs["stderr"].write(b"ERROR\r\n")
                return subprocess.CompletedProcess(argv, 1)
            with patch.object(c.subprocess, "run", side_effect=fake_run):
                r = runner.run("test", ["arping", "-D"], privileged=True)
            self.assertEqual(Path(d, "test.stdout.txt").read_bytes(), b"RAW\r\n")
            self.assertEqual(Path(d, "test.stderr.txt").read_bytes(), b"ERROR\r\n")
            self.assertEqual(r["return_code"], 1)
            self.assertEqual(len(json.loads(Path(d, "COMMANDS.json").read_text())), 1)
            with self.assertRaises(FileExistsError):
                runner.run("test", ["arping", "-D"], privileged=True)

    def test_package_preserves_failure_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d, "evidence"); folder.mkdir()
            (folder / "RESULT.json").write_text('{"status":"STOP"}\n')
            (folder / "raw.stdout.txt").write_bytes(b"raw\r\n")
            archive, sidecar = c.package(folder)
            self.assertEqual(sidecar.read_text().split()[0], hashlib.sha256(archive.read_bytes()).hexdigest())
            with tarfile.open(archive) as t:
                manifest = t.extractfile("evidence/SHA256SUMS").read().decode()
                for line in manifest.splitlines():
                    digest, name = line.split("  ")
                    self.assertEqual(digest, hashlib.sha256(t.extractfile("evidence/" + name).read()).hexdigest())
                self.assertEqual(t.extractfile("evidence/raw.stdout.txt").read(), b"raw\r\n")


class ToolInventoryRegressionTests(unittest.TestCase):
    def main_case(self, hash_error, command_failure=False):
        # Exercise the real main/inventory/inspect/package path, with all server
        # commands replaced by FakeRunner and the login identity simulated.
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            sudo_file = home / "sudo-probe"
            sudo_file.write_bytes(b"temporary tool fixture")
            sudo_file.chmod(0o711)
            original_stat, original_sha = Path.stat, c.sha

            def stat_for_login(path, *args, **kwargs):
                value = original_stat(path, *args, **kwargs)
                if path == home:
                    fields = list(value)
                    fields[4] = 1000  # st_uid for the simulated login home only.
                    return os.stat_result(fields)
                return value

            def sha_for_tool(path):
                if Path(path) == sudo_file:
                    raise hash_error
                return original_sha(path)

            changes = {"01_arping_version": {"return_code": 1,
                       "stderr": "sudo: a password is required\n"}} if command_failure else {}
            runner = FakeRunner(changes)
            with ExitStack() as stack:
                stack.enter_context(patch.object(c.sys, "argv", ["collect_dad.py", "--run"]))
                stack.enter_context(patch.object(c.os, "getuid", return_value=1000))
                stack.enter_context(patch.object(c.os, "geteuid", return_value=1000))
                stack.enter_context(patch.object(c.pwd, "getpwuid", return_value=c.pwd.struct_passwd(
                    ("test-login", "x", 1000, 1000, "", str(home), "/bin/sh"))))
                stack.enter_context(patch.object(Path, "stat", stat_for_login))
                stack.enter_context(patch.object(c.socket, "gethostname", return_value=c.HOST))
                stack.enter_context(patch.object(c, "tools_available", return_value={"sudo": str(sudo_file)}))
                stack.enter_context(patch.object(c, "sha", side_effect=sha_for_tool))
                stack.enter_context(patch.object(c, "Runner", return_value=runner))
                stack.enter_context(patch.object(c.subprocess, "run", side_effect=AssertionError("No real commands")))
                stack.enter_context(redirect_stdout(io.StringIO()))
                rc = c.main()
            folder = next(p for p in home.glob("FDS_P1_LB_01_DAD_*") if p.is_dir())
            result = json.loads((folder / "RESULT.json").read_text())
            inventory = json.loads((folder / "TOOLS.json").read_text()) if (folder / "TOOLS.json").exists() else None
            archive = folder.with_name(folder.name + ".tar.gz")
            self.assertEqual(Path(str(archive) + ".sha256").read_text().split()[0], original_sha(archive))
            for line in (folder / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, original_sha(folder / name))
            return rc, result, inventory, runner.calls

    def test_unreadable_sudo_reaches_inspection_and_preserves_limitation(self):
        rc, result, inventory, calls = self.main_case(PermissionError(errno.EACCES, "Permission denied"))
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED")
        self.assertEqual(result["tool_hash_unavailable"], ["sudo"])
        self.assertIsNone(inventory["sudo"]["sha256"])
        self.assertEqual(inventory["sudo"]["hash_status"], "UNAVAILABLE_PERMISSION_DENIED")
        self.assertEqual(inventory["sudo"]["hash_error"]["errno"], errno.EACCES)
        self.assertEqual(inventory["sudo"]["mode"], "0o711")
        self.assertEqual(sum(name == "05_dad" for name, *_ in calls), 1)

    def test_unreadable_sudo_does_not_mask_command_failure(self):
        rc, result, inventory, calls = self.main_case(PermissionError(errno.EACCES, "Permission denied"), True)
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(result["dad_attempted"])
        self.assertFalse(any(name in ("04_l2_peer", "05_dad") for name, *_ in calls))
        self.assertIsNotNone(inventory)

    def test_other_tool_io_error_still_stops(self):
        rc, result, inventory, calls = self.main_case(OSError(errno.EIO, "Input/output error"))
        self.assertEqual(rc, 2)
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(result["dad_attempted"])
        self.assertFalse(calls)

    def test_readable_tool_hash_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "tool")
            path.write_bytes(b"readable fixture")
            entry = c.tool_metadata({"tool": str(path)})["tool"]
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(entry["hash_status"], "COLLECTED")

    def test_evidence_hash_permission_error_is_not_optional(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d, "evidence")
            folder.mkdir()
            (folder / "RESULT.json").write_text('{"status":"STOP"}\n')
            with patch.object(c, "sha", side_effect=PermissionError(errno.EACCES, "Permission denied")):
                with self.assertRaises(PermissionError):
                    c.package(folder)
            self.assertFalse(folder.with_name(folder.name + ".tar.gz").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
