#!/usr/bin/env python3
"""P1-LB-01: bounded control01 API pre-check; no fault injection. Python 3.8+."""
import argparse
import datetime as dt
import os
from pathlib import Path
import pwd
import shutil
import socket
import sys
import tarfile
import tempfile

from collect_preflight import Runner, Stop, TRUSTED_PATH, json_output, require_ok, sha, stamp, write_json

VERSION = "1.1"
HOST = "k8s-control01"
SOURCE = "10.1.93.102"
ENDPOINT = "https://10.1.93.109:6443"
KUBECONFIG = "/etc/kubernetes/admin.conf"
CONTEXT = "kubernetes-admin@kubernetes"
NODES = {"k8s-control01", "k8s-control02", "k8s-control03",
         "k8s-worker01", "k8s-worker02", "k8s-worker03"}
# Emit only boolean flags. Never emit kubeconfig, credentials, proxy URL or exec arguments.
# Raw strings preserve Go string escapes; Python must not insert a literal newline inside {{"..."}}.
CONFIG_TEMPLATE = ('{{range .clusters}}'
    r'{{if index .cluster "proxy-url"}}proxy=yes{{else}}proxy=no{{end}}{{"\n"}}'
    r'{{if index .cluster "insecure-skip-tls-verify"}}insecure=yes{{else}}insecure=no{{end}}{{"\n"}}'
    r'{{if or (index .cluster "certificate-authority") (index .cluster "certificate-authority-data")}}ca=yes{{else}}ca=no{{end}}{{"\n"}}'
    '{{end}}{{range .users}}'
    r'{{if .user.exec}}exec=yes{{else}}exec=no{{end}}{{"\n"}}'
    r'{{if index .user "auth-provider"}}provider=yes{{else}}provider=no{{end}}{{"\n"}}'
    r'{{if or (index .user "as") (index .user "as-uid") (index .user "as-groups") (index .user "as-user-extra")}}impersonation=yes{{else}}impersonation=no{{end}}{{"\n"}}'
    '{{end}}')
EXPECTED_FLAGS = ["proxy=no", "insecure=no", "ca=yes", "exec=no", "provider=no", "impersonation=no"]


def verify_route(data):
    if (not isinstance(data, list) or len(data) != 1 or
            data[0].get("prefsrc") != SOURCE or data[0].get("dst") != "10.1.93.109" or
            data[0].get("type") in ("blackhole", "unreachable", "prohibit")):
        raise Stop("UNEXPECTED_ROUTE_SOURCE")
    return {"route_selected_source": SOURCE, "device": data[0].get("dev"),
            "lb_observed_source": "NOT_CAPTURED"}


def verify_nodes(data):
    if data.get("kind") != "NodeList" or data.get("metadata", {}).get("continue"):
        raise Stop("INCOMPLETE_NODE_LIST")
    items = data.get("items", [])
    if len(items) != 6 or {x.get("metadata", {}).get("name") for x in items} != NODES:
        raise Stop("NODE_SET_DIFFERS_FROM_EXPECTED_SIX")
    ready = {}
    for item in items:
        conditions = [x.get("status") for x in item.get("status", {}).get("conditions", [])
                      if x.get("type") == "Ready"]
        ready[item["metadata"]["name"]] = conditions == ["True"]
    if not all(ready.values()):
        raise Stop("ONE_OR_MORE_NODES_NOT_READY")
    return ready


def inspect(runner, hostname, expected_user, cache_dir):
    result = {"status": "STOP", "authenticated_identity": "NOT_VERIFIED",
              "api_read": "NOT_VERIFIED", "node_readiness": "NOT_VERIFIED",
              "stage_b": "NOT_COMPLETED", "fault_injection": "NOT_RUN"}
    try:
        if hostname.split(".")[0] != HOST:
            raise Stop("WRONG_HOST_EXPECTED_" + HOST)
        result["route"] = verify_route(json_output(runner.run("01_route", ["ip", "-j", "-4", "route", "get", "10.1.93.109"])))
        local = ["kubectl", "--kubeconfig=" + KUBECONFIG, "--context=" + CONTEXT,
                 "--cache-dir=" + str(cache_dir)]
        flags = require_ok(runner.run("02_config_flags", local + ["config", "view", "--minify",
                    "-o", "go-template=" + CONFIG_TEMPLATE], privileged=True)).splitlines()
        if flags != EXPECTED_FLAGS:
            raise Stop("CONFIG_FLAGS_REQUIRE_REVIEW")
        require_ok(runner.run("03_client_version", ["kubectl", "version", "--client", "-o", "json"]))
        remote = local + ["--server=" + ENDPOINT, "--tls-server-name=10.1.93.109",
                          "--insecure-skip-tls-verify=false", "--request-timeout=5s"]
        who = json_output(runner.run("04_whoami", remote + ["auth", "whoami", "-o", "json"], privileged=True))
        userinfo = who.get("status", {}).get("userInfo", {})
        username = userinfo.get("username")
        result["observed_username"] = username
        if (not username or username != expected_user or username == "system:anonymous" or
                "system:unauthenticated" in userinfo.get("groups", [])):
            raise Stop("IDENTITY_MISMATCH_OR_ANONYMOUS")
        result["authenticated_identity"] = "MATCH"
        nodes = json_output(runner.run("05_nodes", remote + ["get", "--raw=/api/v1/nodes?limit=20"], privileged=True))
        result["api_read"] = "SUCCESS"
        result["nodes"] = verify_nodes(nodes)
        result["node_readiness"] = "SIX_READY"
        readyz = require_ok(runner.run("06_readyz", remote + ["get", "--raw=/readyz"], privileged=True)).strip()
        if readyz != "ok":
            raise Stop("READYZ_NOT_OK")
        result["readyz"] = "ok"
        after = verify_route(json_output(runner.run("07_route_after", ["ip", "-j", "-4", "route", "get", "10.1.93.109"])))
        if result["route"] != after:
            raise Stop("ROUTE_CHANGED_DURING_PRECHECK")
        result["status"] = "API_PRECHECK_READY"
    except (Exception, KeyboardInterrupt) as exc:
        result["reason"] = type(exc).__name__ + ": " + str(exc)
    return result


def package(folder):
    # Only top-level original logs and metadata: public discovery cache is excluded.
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (folder / "SHA256SUMS").write_text("".join(sha(p) + "  " + p.name + "\n" for p in files))
    archive = folder.with_name(folder.name + ".tar.gz")
    with tarfile.open(archive, "x:gz") as tar:
        for path in files + [folder / "SHA256SUMS"]:
            tar.add(path, arcname=folder.name + "/" + path.name, recursive=False)
    sidecar = archive.with_name(archive.name + ".sha256")
    with sidecar.open("x") as f:
        f.write(sha(archive) + "  " + archive.name + "\n")
    return archive, sidecar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--expected-user", required=True, help="existing approved identity, not a new grant")
    args = parser.parse_args()
    if not args.run or os.getuid() == 0 or os.geteuid() == 0:
        print("STOP: normal control01 login account, sudo -v first; no sudo python3.", file=sys.stderr)
        return 2
    if not args.expected_user.strip() or args.expected_user == "system:anonymous":
        print("STOP: a non-anonymous expected identity is required.", file=sys.stderr)
        return 2
    os.umask(0o077)
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir).resolve()
    if not home.is_dir() or home.stat().st_uid != os.getuid():
        print("STOP: login home unavailable or ownership mismatch.", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="FDS_P1_LB_01_API_PRECHECK_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_", dir=home))
    write_json(folder / "METADATA.json", {"version": VERSION, "started": stamp(), "hostname": socket.gethostname(),
               "account": account.pw_name, "uid": os.getuid(), "endpoint": ENDPOINT,
               "context": CONTEXT, "expected_user": args.expected_user,
               "configuration_changes_attempted": False, "collector_sha256": sha(Path(__file__).resolve()),
               "helper_sha256": sha(Path(__file__).resolve().with_name("collect_preflight.py")),
               "helper_source_commit": "41b33b138d5e8a1dce3d4b2d9a3d7ed30afd72ed"})
    for name in ("collect_api_precheck.py", "collect_preflight.py"):
        shutil.copyfile(Path(__file__).resolve().with_name(name), folder / name)
    try:
        binaries = {}
        for name in ("ip", "kubectl", "sudo", "env", "timeout"):
            path = shutil.which(name, path=TRUSTED_PATH + ":/usr/local/bin")
            if not path:
                raise Stop("MISSING_TOOL: " + name + "; no installation attempted")
            binaries[name] = str(Path(path).resolve())
        cache_dir = folder / "kubectl-cache"
        cache_dir.mkdir(mode=0o700)
        write_json(folder / "TOOLS.json", binaries)
        result = inspect(Runner(folder, binaries), socket.gethostname(), args.expected_user, cache_dir)
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "STOP", "reason": type(exc).__name__ + ": " + str(exc), "stage_b": "NOT_COMPLETED"}
    result["finished"] = stamp()
    write_json(folder / "RESULT.json", result)
    try:
        archive, sidecar = package(folder)
    except Exception as exc:
        print("STOP: package failed, preserve " + str(folder) + ": " + str(exc), file=sys.stderr)
        return 2
    print("STATUS=" + result["status"])
    if result.get("reason"):
        print("REASON=" + result["reason"])
    print("ARCHIVE=" + str(archive))
    print("SIDECAR=" + str(sidecar))
    return 0 if result["status"] == "API_PRECHECK_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
