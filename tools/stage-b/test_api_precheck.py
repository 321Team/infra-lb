import copy
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import collect_api_precheck as api


def nodes():
    return {"kind": "NodeList", "metadata": {}, "items": [
        {"metadata": {"name": name}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        for name in sorted(api.NODES)]}


class FakeRunner:
    def __init__(self, overrides=None):
        self.calls = []
        route = json.dumps([{"dst": "10.1.93.109", "prefsrc": api.SOURCE, "dev": "ens160"}])
        self.output = {"01_route": route, "02_config_flags": "\n".join(api.EXPECTED_FLAGS) + "\n",
                       "03_client_version": "{}", "04_whoami": json.dumps({"status": {"userInfo": {
                           "username": "kubernetes-admin", "groups": ["system:authenticated"]}}}),
                       "05_nodes": json.dumps(nodes()), "06_readyz": "ok\n", "07_route_after": route}
        self.overrides = overrides or {}

    def run(self, name, args, privileged=False):
        self.calls.append((name, args, privileged))
        record = {"name": name, "return_code": 0, "stdout": self.output[name], "stderr": ""}
        record.update(self.overrides.get(name, {}))
        return record


class ApiPrecheckTests(unittest.TestCase):
    def run_case(self, overrides=None, host=api.HOST):
        runner = FakeRunner(overrides)
        return api.inspect(runner, host, "kubernetes-admin", Path("/test/cache")), runner

    def test_ready_is_not_stage_b_acceptance(self):
        result, runner = self.run_case()
        self.assertEqual(result["status"], "API_PRECHECK_READY")
        self.assertEqual(result["stage_b"], "NOT_COMPLETED")
        self.assertEqual(result["fault_injection"], "NOT_RUN")
        self.assertEqual(len(runner.calls), 7)
        for name, args, privileged in runner.calls:
            if name in ("04_whoami", "05_nodes", "06_readyz"):
                self.assertTrue(privileged)
                self.assertIn("--insecure-skip-tls-verify=false", args)
                self.assertIn("--server=" + api.ENDPOINT, args)
                self.assertIn("--tls-server-name=10.1.93.109", args)

    def test_wrong_host_makes_no_calls(self):
        result, runner = self.run_case(host="ansible01")
        self.assertEqual(result["status"], "STOP")
        self.assertFalse(runner.calls)

    def test_route_negative_source_stops_before_credentials(self):
        result, runner = self.run_case({"01_route": {"stdout": '[{"dst":"10.1.93.109","prefsrc":"10.250.10.10"}]'}})
        self.assertEqual(result["status"], "STOP")
        self.assertEqual(len(runner.calls), 1)

    def test_config_flags_stop_before_remote_requests(self):
        for old, new in [("proxy=no", "proxy=yes"), ("insecure=no", "insecure=yes"),
                         ("ca=yes", "ca=no"), ("exec=no", "exec=yes"),
                         ("provider=no", "provider=yes"), ("impersonation=no", "impersonation=yes")]:
            with self.subTest(flag=old):
                out = "\n".join(api.EXPECTED_FLAGS).replace(old, new)
                result, runner = self.run_case({"02_config_flags": {"stdout": out}})
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(len(runner.calls), 2)

    def test_auth_failures_never_progress_to_nodes(self):
        for override in [{"return_code": 1, "stderr": "Forbidden"}, {"outer_timeout": True},
                         {"stdout": "not-json"}, {"stdout": json.dumps({"status": {"userInfo": {"username": "system:anonymous"}}})},
                         {"stdout": json.dumps({"status": {"userInfo": {"username": "other"}}})}]:
            with self.subTest(override=override):
                result, runner = self.run_case({"04_whoami": override})
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(runner.calls[-1][0], "04_whoami")

    def test_get_forbidden_preserves_identity_success(self):
        result, _ = self.run_case({"05_nodes": {"return_code": 1, "stderr": "Forbidden"}})
        self.assertEqual(result["authenticated_identity"], "MATCH")
        self.assertEqual(result["api_read"], "NOT_VERIFIED")
        self.assertEqual(result["status"], "STOP")

    def test_partial_list_and_bad_readiness_stop(self):
        a = nodes(); a["metadata"]["continue"] = "next"
        b = nodes(); b["items"] = b["items"][:-1]
        c = nodes(); c["items"][0]["status"]["conditions"][0]["status"] = "False"
        d = nodes(); d["items"][0] = copy.deepcopy(d["items"][1])
        for value in (a, b, c, d):
            with self.subTest(value=value):
                result, runner = self.run_case({"05_nodes": {"stdout": json.dumps(value)}})
                self.assertEqual(result["status"], "STOP")
                self.assertEqual(result["api_read"], "SUCCESS")
                self.assertEqual(runner.calls[-1][0], "05_nodes")

    def test_tls_or_readyz_failure_not_pass(self):
        result, _ = self.run_case({"06_readyz": {"return_code": 1, "stderr": "x509"}})
        self.assertEqual(result["status"], "STOP")

    def test_route_drift_not_pass(self):
        result, _ = self.run_case({"07_route_after": {"stdout": '[{"dst":"10.1.93.109","prefsrc":"10.1.93.102","dev":"other"}]'}})
        self.assertEqual(result["status"], "STOP")

    def test_bundle_excludes_cache_and_covers_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "evidence"; folder.mkdir()
            (folder / "failure.stderr.txt").write_bytes(b"TLS failure\n")
            (folder / "kubectl-cache").mkdir()
            (folder / "kubectl-cache" / "ignored").write_text("not evidence")
            archive, sidecar = api.package(folder)
            self.assertEqual(sidecar.read_text().split()[0], api.sha(archive))
            with tarfile.open(archive) as tar:
                self.assertEqual(set(tar.getnames()), {"evidence/failure.stderr.txt", "evidence/SHA256SUMS"})
                self.assertEqual(tar.extractfile("evidence/failure.stderr.txt").read(), b"TLS failure\n")
            line = (folder / "SHA256SUMS").read_text().split()
            self.assertEqual(line, [api.sha(folder / "failure.stderr.txt"), "failure.stderr.txt"])


if __name__ == "__main__":
    unittest.main()
