"""Finite control01 observer. Existing credentials; no CP configuration changes."""
import json
import socket
import time

import collect_api_precheck as api
from collect_preflight import Stop, json_output, require_ok, stamp
from stageb_common import (MAX_RUN_SECONDS, SAMPLE_SECONDS, MAX_SAMPLE_SECONDS,
                           RuntimeRunner, atomic, binaries, failure_budget_exceeded, state)


def run(folder, data):
    r = RuntimeRunner(folder, binaries(["ip", "kubectl", "sudo", "env", "timeout"]), seconds=5)
    cache = folder / "kubectl-cache"
    cache.mkdir(mode=0o700)
    sequence = 0
    try:
        precheck = api.inspect(r, socket.gethostname(), "kubernetes-admin", cache)
        atomic(folder / "PRECHECK.json", precheck)
        if precheck["status"] != "API_PRECHECK_READY":
            raise Stop("API_PRECHECK_FAILED: " + precheck.get("reason", "unknown"))
        remote = ["kubectl", "--kubeconfig=" + api.KUBECONFIG, "--context=" + api.CONTEXT,
                  "--cache-dir=" + str(cache), "--server=" + api.ENDPOINT,
                  "--tls-server-name=10.1.93.109", "--insecure-skip-tls-verify=false", "--request-timeout=3s"]
        began = time.monotonic()
        previous_start = None
        samples = []
        while time.monotonic() - began < MAX_RUN_SECONDS:
            if (folder / "STOP").exists():
                state(folder, "OBSERVER_COMPLETE", sequence=sequence, reason="CONTROLLER_STOP_REQUEST",
                      failed_sample_count=sum(1 for s in samples if not s["success"]))
                return
            sequence += 1
            start = time.monotonic()
            sample = dict(sequence=sequence, started=stamp(), start_monotonic=start, success=False)
            try:
                if previous_start is not None and start - previous_start > MAX_SAMPLE_SECONDS:
                    raise Stop("SAMPLE_GAP_EXCEEDED_7_SECONDS")
                previous_start = start
                nodes = json_output(r.run("sample_%04d_nodes" % sequence,
                                         remote + ["get", "--raw=/api/v1/nodes?limit=20"], privileged=True))
                api.verify_nodes(nodes)
                ready = require_ok(r.run("sample_%04d_readyz" % sequence,
                                         remote + ["get", "--raw=/readyz"], privileged=True)).strip()
                if ready != "ok":
                    raise Stop("READYZ_NOT_OK")
                if time.monotonic() - start > MAX_SAMPLE_SECONDS:
                    raise Stop("SAMPLE_DURATION_EXCEEDED_7_SECONDS")
                sample["success"] = True
            except Exception as exc:
                # A bounded number/duration of failed samples is expected while
                # HAProxy is still detecting the injected fault (inter 2s/fall 3
                # takes several seconds); do not abort the whole run for that.
                # The confirmed budget below still stops on a real outage.
                sample["reason"] = type(exc).__name__ + ": " + str(exc)
            finally:
                sample.update(finished=stamp(), end_monotonic=time.monotonic())
                samples.append(sample)
                with (folder / "SAMPLES.jsonl").open("a") as f:
                    f.write(json.dumps(sample) + "\n")
            state(folder, "OBSERVING", sequence=sequence, sample=sample, run_id=data["run_id"])
            if not sample["success"]:
                reason = failure_budget_exceeded(samples, data)
                if reason:
                    raise Stop(reason)
            time.sleep(max(0, SAMPLE_SECONDS - (time.monotonic() - start)))
        raise Stop("OBSERVER_240_SECOND_LIMIT")
    except BaseException as exc:
        state(folder, "STOP", sequence=sequence, reason=type(exc).__name__ + ": " + str(exc))
