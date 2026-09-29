"""Readiness tests do not invoke Ansible, SSH, sudo or nft."""
import copy
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from collect_preflight import Stop
import collect_stageb_readiness as check


class Fake:
    def __init__(self, case):
        self.case, self.calls = case, []

    def run(self, name, args, privileged=False, input_bytes=None):
        self.calls.append((name, args, input_bytes))
        rc = 0
        if "tables" in args:
            result = {"nftables": [{"table": {"name": "firewalld", "family": "inet"}}]}
            if self.case == "existing":
                result["nftables"].append({"table": {"name": "p1lb_old", "family": "inet"}})
            if self.case == "malformed":
                result = {}
            output = json.dumps(result)
        elif "ruleset" in args:
            output = json.dumps({"nftables": [{"metainfo": {"test_only": True}}]})
            if self.case == "drift" and name.startswith("06"):
                output = json.dumps({"nftables": []})
        elif "--version" in args:
            output = "nftables MOCK_ONLY"
        elif "-c" in args:
            rc = 2 if self.case == "rejected" else 0
            output = ""
        else:
            raise AssertionError("Unexpected or mutating command: " + str(args))
        return {"name": name, "return_code": rc, "stdout": output, "stderr": "", "outer_timeout": False}


class ReadinessTests(unittest.TestCase):
    def test_lb_user_matches_runtime_account(self):
        self.assertEqual(check.LB_USER, "server01_k8s--api-lb")

    def test_nft_check_has_no_apply_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Fake("pass")
            result = check.inspect_nft(runner, Path(tmp), "a" * 32)
            self.assertEqual(result["status"], "NFT_CHECK_ONLY_PASS")
            self.assertEqual(result["fault_injection"], "NOT_RUN")
            submits = [args for _, args, payload in runner.calls if payload]
            self.assertEqual(submits, [["nft", "-c", "-f", "-"]])

    def test_check_failure_still_collects_post_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Fake("rejected")
            with self.assertRaises(Stop):
                check.inspect_nft(runner, Path(tmp), "a" * 32)
            self.assertEqual(runner.calls[-1][0], "06_rules_after")

    def test_drift_or_existing_test_table_or_malformed_list_stops(self):
        for case in ["drift", "existing", "malformed"]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp, self.assertRaises(Stop):
                check.inspect_nft(Fake(case), Path(tmp), "a" * 32)

    def test_ansible_probe_uses_fixed_one_host_noninteractive_no_become(self):
        key = Path("/tmp/mock-only-key")
        args = check.ansible_args("/usr/bin/ansible", Path("/tmp/mock-only"), key)
        self.assertEqual(args[1], "10.1.93.109")
        self.assertEqual(args[args.index("-i") + 1], "10.1.93.109,")
        extra = json.loads(args[args.index("-e") + 1])
        self.assertFalse(extra["ansible_become"])
        self.assertFalse(extra["ansible_ssh_use_tty"])
        self.assertEqual(extra["ansible_user"], check.LB_USER)
        self.assertIn("StrictHostKeyChecking=yes", extra["ansible_ssh_common_args"])
        self.assertIn("BatchMode=yes", extra["ansible_ssh_common_args"])
        self.assertIn("IdentitiesOnly=yes", extra["ansible_ssh_common_args"])
        self.assertIn("RequestTTY=no", extra["ansible_ssh_common_args"])
        self.assertEqual(args[args.index("--private-key") + 1], str(key))
        self.assertNotIn("--ask-pass", args)

    def test_actual_identity_and_failed_result_are_not_overridden_by_rc0(self):
        identity = {"host": "k8s-api-lb01", "user": check.LB_USER, "uid": 1001, "euid": 1001}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result"
            path.write_text(json.dumps({"rc": 0, "stdout": json.dumps(identity)}))
            self.assertEqual(check.parse_ansible_result(path), identity)
            for field, value in [("host", "wrong"), ("user", "root"), ("uid", 0), ("euid", 0)]:
                bad = dict(identity, **{field: value})
                path.write_text(json.dumps({"rc": 0, "stdout": json.dumps(bad)}))
                with self.assertRaises(Stop):
                    check.parse_ansible_result(path)
            path.write_text(json.dumps({"rc": 0, "unreachable": True, "stdout": json.dumps(identity)}))
            with self.assertRaises(Stop):
                check.parse_ansible_result(path)

    def test_package_covers_every_included_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            folder.mkdir()
            (folder / "RESULT.json").write_text('{"status":"STOP"}')
            (folder / "LB_IDENTITY_RESULT.json").write_text('{"unreachable":true}')
            (folder / "ansible-result").mkdir()
            (folder / "ansible-result" / "10.1.93.109").write_text("not duplicated")
            archive, sidecar = check.package(folder)
            self.assertEqual(sidecar.read_text().split()[0], check.sha(archive))
            with tarfile.open(archive) as tar:
                values = {m.name.split("/", 1)[1]: tar.extractfile(m).read() for m in tar.getmembers()}
            listed = {line.split("  ")[1] for line in values.pop("SHA256SUMS").decode().splitlines()}
            self.assertEqual(set(values), listed)
            self.assertEqual(len(values), 2)


if __name__ == "__main__":
    unittest.main()
