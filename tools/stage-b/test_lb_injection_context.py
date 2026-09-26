import json
import unittest
from unittest.mock import patch

import collect_lb_injection_context as context


class FakeRunner:
    def __init__(self, overrides=None):
        self.tools = {name: "/usr/bin/" + name for name in
                      ("cat", "systemctl", "ip", "nft", "firewall-cmd")}
        self.calls = []
        self.overrides = overrides or {}

    def run(self, name, args, privileged=False):
        self.calls.append((name, args, privileged))
        out = "mock observed data\n"
        if args[0] == "ip":
            out = json.dumps([{"dst": args[-1], "prefsrc": context.base.TARGET, "dev": "ens160"}])
        elif args[0] == "nft" and "list" in args:
            out = '{"nftables":[{"table":{"family":"inet","name":"firewalld"}}]}'
        elif "--state" in args:
            out = "running\n"
        record = {"name": name, "return_code": 0, "stdout": out, "stderr": ""}
        override = self.overrides.get(name, {})
        if isinstance(override, BaseException):
            raise override
        record.update(override)
        return record


class ContextTests(unittest.TestCase):
    def collect(self, runner=None, preflight="PRECHECK_READY", host=None):
        runner = runner or FakeRunner()
        with patch.object(context.base, "inspect", return_value={"status": preflight}) as inspect:
            result = context.collect(runner, host or context.base.HOST)
        return result, runner, inspect

    def test_complete_means_data_only_and_queries_are_read_only(self):
        result, runner, _ = self.collect()
        self.assertEqual(result["status"], "PREPARATION_DATA_COLLECTED")
        self.assertEqual(result["injection_ready"], "NOT_EVALUATED")
        self.assertEqual(result["injection"], "NOT_RUN")
        self.assertEqual(result["stage_b"], "NOT_COMPLETED")
        for _, args, _ in runner.calls:
            self.assertFalse(set(args) & {"add", "insert", "delete", "flush", "reload", "restart", "start", "stop", "enable"})
            if args[0] == "nft":
                self.assertIn(args[1:], [["--version"], ["-j", "-a", "list", "ruleset"]])
        self.assertTrue(any(args == ["firewall-cmd", "--permanent", "--list-all-zones"] for _, args, _ in runner.calls))

    def test_cp_host_rejected_before_all_queries(self):
        result, runner, inspect = self.collect(host="k8s-control01")
        self.assertEqual(result["status"], "STOP")
        inspect.assert_not_called()
        self.assertEqual(runner.calls, [])

    def test_preflight_stop_skips_firewall(self):
        result, runner, _ = self.collect(preflight="STOP")
        self.assertEqual(result["status"], "STOP")
        self.assertEqual(runner.calls, [])

    def test_backend_down_still_collects_context_but_not_ready(self):
        result, runner, _ = self.collect(preflight="PRECHECK_NOT_READY")
        self.assertEqual(result["status"], "PREPARATION_INCOMPLETE")
        self.assertTrue(runner.calls)

    def test_missing_nft_nonzero_timeout_and_invalid_json_cannot_pass(self):
        for override in [{"return_code": 1, "stderr": "Operation not permitted"},
                         {"outer_timeout": True}, {"stdout": "invalid"}, {"stdout": "{}"}]:
            with self.subTest(override=override):
                result, _, _ = self.collect(FakeRunner({"14_nft_ruleset": override}))
                self.assertEqual(result["status"], "PREPARATION_INCOMPLETE")
        runner = FakeRunner(); del runner.tools["nft"]
        result, _, _ = self.collect(runner)
        self.assertEqual(result["status"], "PREPARATION_INCOMPLETE")

    def test_firewalld_inactive_does_not_start_or_query_zones(self):
        runner = FakeRunner({"16_firewalld_state": {"return_code": 252, "stderr": "not running"}})
        result, runner, _ = self.collect(runner)
        self.assertEqual(result["status"], "PREPARATION_INCOMPLETE")
        self.assertFalse(any("--list-all-zones" in args or "start" in args for _, args, _ in runner.calls))

    def test_route_or_service_drift_is_incomplete(self):
        for override in [{"12_route_1": {"stdout": '[{"dst":"10.1.93.102","prefsrc":"10.250.10.10"}]'}},
                         {"20_firewall_units_after": {"stdout": "changed"}}]:
            result, _, _ = self.collect(FakeRunner(override))
            self.assertEqual(result["status"], "PREPARATION_INCOMPLETE")

    def test_interrupt_preserves_stop_state(self):
        result, _, _ = self.collect(FakeRunner({"14_nft_ruleset": KeyboardInterrupt()}))
        self.assertEqual(result["status"], "STOP")
        self.assertIn("KeyboardInterrupt", result["context_errors"][0])


if __name__ == "__main__":
    unittest.main()
