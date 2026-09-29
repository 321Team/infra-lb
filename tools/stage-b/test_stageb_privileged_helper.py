"""Local-only policy tests for the Stage B privileged helper. Never runs sudo or nft."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import stageb_common as common
import stageb_privileged_helper as helper
import stageb_rules


class HelperPolicyTests(unittest.TestCase):
    def test_expected_sudo_user_matches_runtime_account(self):
        self.assertEqual(helper.EXPECTED_SUDO_USER, "server01_k8s--api-lb")

    def test_sudoers_principal_matches_runtime_account(self):
        policy = Path(__file__).with_name("stageb_privilege.sudoers").read_text()
        self.assertIn("server01_k8s--api-lb ALL=(root) NOPASSWD:", policy)
        self.assertNotIn("server01_k8s-api-lb ALL=(root) NOPASSWD:", policy)

    def accepted(self, argv, payload=b""):
        helper._shape(argv, payload)

    def rejected(self, argv, payload=b""):
        with self.assertRaises(helper.Stop):
            helper._shape(argv, payload)

    def test_only_exact_proc_cmdline_is_allowed(self):
        self.accepted(["/usr/bin/cat", "/proc/1273/cmdline"])
        self.rejected(["/usr/bin/cat", "/etc/shadow"])
        self.rejected(["/usr/bin/cat", "/proc/1/status"])

    def test_stats_socket_and_input_are_fixed(self):
        argv = ["/usr/bin/socat", "-T", "1", "-", "UNIX-CONNECT:/var/lib/haproxy/stats"]
        self.accepted(argv, b"show stat\n")
        self.rejected(argv, b"show info\n")
        self.rejected(["/usr/bin/socat", "-T", "1", "-", "TCP:10.1.93.104:6443"], b"show stat\n")

    def test_helper_rule_bytes_match_canonical_renderer(self):
        for run_id in ("a" * 32, "0123456789abcdef" * 2):
            self.assertEqual(helper.rules(run_id), stageb_rules.rules(run_id))

    def test_cmdline_request_is_bound_to_current_haproxy_pid(self):
        with patch.object(helper, "trusted_binary", return_value="/usr/bin/cat"), \
             patch.object(helper, "current_haproxy_pid", return_value="1273"):
            helper.validate_request(["/usr/bin/cat", "/proc/1273/cmdline"], b"")
            with self.assertRaises(helper.Stop):
                helper.validate_request(["/usr/bin/cat", "/proc/1274/cmdline"], b"")

    def test_nft_accepts_only_exact_bounded_stageb_rules(self):
        run_id = "a" * 32
        payload = helper.rules(run_id)
        self.accepted(["/usr/sbin/nft", "-c", "-f", "-"], payload)
        self.accepted(["/usr/sbin/nft", "-f", "-"], payload)
        self.accepted(["/usr/sbin/nft", "-j", "list", "table", "inet", "p1lb_" + run_id])
        self.accepted(["/usr/sbin/nft", "delete", "table", "inet", "p1lb_" + run_id])
        self.rejected(["/usr/sbin/nft", "flush", "ruleset"])
        self.rejected(["/usr/sbin/nft", "-f", "-"], payload.replace(b"10.1.93.104", b"10.1.93.103"))
        self.rejected(["/usr/sbin/nft", "delete", "table", "inet", "firewalld"])

    def test_config_hash_paths_cannot_escape_haproxy_scope(self):
        self.accepted(["/usr/bin/sha256sum", "--", "/etc/haproxy/haproxy.cfg",
                       "/etc/haproxy/conf.d/kubernetes.cfg"])
        self.rejected(["/usr/bin/sha256sum", "--", "/etc/shadow"])
        self.rejected(["/usr/bin/sha256sum", "--", "/etc/haproxy/haproxy.cfg",
                       "/tmp/other.cfg"])

    def test_source_set_binds_helper_bytes(self):
        self.assertIn("stageb_privileged_helper.py", common.source_files())
        self.assertIn("stageb_privilege.sudoers", common.source_files())

    def test_runtime_runner_routes_privileged_command_through_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = common.RuntimeRunner(Path(tmp),
                {"sudo": "/usr/bin/sudo", "nft": "/usr/sbin/nft"},
                helper_sha="b" * 64, policy_sha="c" * 64)
            with patch.object(common.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                result = runner.run("tables", ["nft", "-j", "list", "tables"], privileged=True)
            self.assertEqual(result["return_code"], 0)
            self.assertEqual(run.call_args.args[0], [
                "/usr/bin/sudo", "-n", "--", common.PRIVILEGED_HELPER,
                "--expected-sha", "b" * 64,
                "--expected-policy-sha", "c" * 64, "--",
                "/usr/sbin/nft", "-j", "list", "tables"
            ])

    def test_policy_file_is_part_of_runtime_source_binding(self):
        self.assertIn(common.PRIVILEGED_POLICY_SOURCE, common.source_files())

    def test_cp_legacy_privileged_path_is_unchanged_without_helper_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = common.RuntimeRunner(Path(tmp),
                {"sudo": "/usr/bin/sudo", "env": "/usr/bin/env", "timeout": "/usr/bin/timeout",
                 "kubectl": "/usr/bin/kubectl"}, seconds=5)
            with patch.object(common.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                result = runner.run("cp", ["kubectl", "get", "--raw=/readyz"], privileged=True)
            self.assertEqual(result["return_code"], 0)
            self.assertEqual(run.call_args.args[0][:8], [
                "/usr/bin/sudo", "-n", "--", "/usr/bin/env", "-i",
                "PATH=" + common.TRUSTED_PATH, "LC_ALL=C", "LANG=C"
            ])
            self.assertNotIn(common.PRIVILEGED_HELPER, run.call_args.args[0])

    def test_privileged_command_without_reviewed_helper_sha_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = common.RuntimeRunner(Path(tmp), {"sudo": "/usr/bin/sudo", "nft": "/usr/sbin/nft"},
                                          helper_sha="b" * 64, require_helper=True)
            with self.assertRaises(common.Stop):
                runner.run("tables", ["nft", "-j", "list", "tables"], privileged=True)


if __name__ == "__main__":
    unittest.main()
