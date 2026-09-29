import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name("collect_cp_reboot_haproxy_history.py")
spec = importlib.util.spec_from_file_location("collector", MODULE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class ParserTests(unittest.TestCase):
    def test_expected_lb_account(self):
        self.assertEqual(collector.EXPECTED_USER, "server01_k8s-api-lb")

    def test_down_up_pair(self):
        text = (
            "2026-09-27T08:36:41.100000+00:00 host haproxy[100]: "
            "Server kubernetes_api_backend/k8s-control03 is DOWN, reason: Layer4 timeout\n"
            "2026-09-27T08:36:47.100000+00:00 host haproxy[100]: "
            "Server kubernetes_api_backend/k8s-control03 is UP, reason: Layer4 check passed\n"
        )
        rows = collector.extract_transitions(text)
        self.assertEqual([r["state"] for r in rows], ["DOWN", "UP"])
        summary = collector.summarize(rows)
        self.assertEqual(summary["historical_window_verdict"], "DOWN_UP_PAIR_FOUND")
        self.assertEqual(summary["down_to_up_seconds"], 6.0)

    def test_unrelated_backend_ignored(self):
        text = (
            "2026-09-27T08:36:41+00:00 host haproxy[100]: "
            "Server kubernetes_api_backend/k8s-control02 is DOWN, reason: Layer4 timeout\n"
        )
        self.assertEqual(collector.extract_transitions(text), [])

    def test_missing_timestamp_is_not_duration_evidence(self):
        rows = collector.extract_transitions(
            "Server kubernetes_api_backend/k8s-control03 is DOWN\n"
            "Server kubernetes_api_backend/k8s-control03 is UP\n"
        )
        summary = collector.summarize(rows)
        self.assertEqual(summary["historical_window_verdict"], "INSUFFICIENT_NO_DOWN_UP_PAIR")
        self.assertIsNone(summary["down_to_up_seconds"])


if __name__ == "__main__":
    unittest.main()
