"""Shared bounded runtime support. No network mutation in this module."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import time

from collect_preflight import Stop, TRUSTED_PATH, ENV, sha, stamp

LEASE_SECONDS = 10
SAMPLE_SECONDS = 2
MAX_SAMPLE_SECONDS = 7
MAX_RUN_SECONDS = 240
TERMINAL = {"PASS_CANDIDATE", "STOP", "OBSERVER_COMPLETE"}


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + ".new." + str(os.getpid()))
    with temp.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(temp), str(path))


def read(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def validate_inputs(data, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not re.fullmatch(r"[0-9a-f]{32}", data.get("run_id", "")):
        raise Stop("INVALID_RUN_ID")
    if not re.fullmatch(r"[0-9a-f]{40}", data.get("source_revision", "")):
        raise Stop("SOURCE_REVISION_REQUIRED")
    if data.get("reviewed_revision") != data["source_revision"]:
        raise Stop("REVIEWED_SOURCE_MISMATCH")
    if data.get("runtime_authorized") is not True:
        raise Stop("LEAD_RUNTIME_DECISION_REQUIRED")
    for key in ("review_reference", "lead", "oob_reference"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise Stop("MISSING_" + key.upper())
    if data.get("target") != "10.1.93.104:6443":
        raise Stop("THIS_SOURCE_SUPPORTS_ONLY_CONTROL03")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", data.get("lb_user", "")) or data["lb_user"] == "root":
        raise Stop("EXISTING_NONROOT_LB_ACCOUNT_REQUIRED")
    try:
        start = dt.datetime.fromisoformat(data["window_start_kst"])
        end = dt.datetime.fromisoformat(data["window_end_kst"])
        if any(x.utcoffset() != dt.timedelta(hours=9) for x in (start, end)):
            raise ValueError("KST offset required")
    except (KeyError, ValueError, TypeError) as exc:
        raise Stop("EXPLICIT_KST_WINDOW_REQUIRED") from exc
    if not start <= now < end or (end - now).total_seconds() < MAX_RUN_SECONDS + 60:
        raise Stop("OUTSIDE_WINDOW_OR_LESS_THAN_300_SECONDS_REMAIN")
    return end


def local_identity(role, data):
    account = pwd.getpwuid(os.getuid())
    expected = ("k8s-control01", "svc_ansible") if role == "cp" else ("k8s-api-lb01", data["lb_user"])
    if (socket.gethostname().split(".")[0], account.pw_name) != expected or os.getuid() == 0 or os.geteuid() != os.getuid():
        raise Stop("WRONG_HOST_OR_LOGIN_ACCOUNT")
    home = Path(account.pw_dir).resolve()
    if home.stat().st_uid != os.getuid():
        raise Stop("HOME_OWNERSHIP_MISMATCH")
    return home


def work(data, role, create=False):
    home = local_identity(role, data)
    path = home / ("P1_LB_STAGEB_" + data["run_id"])
    if create:
        path.mkdir(mode=0o700, exist_ok=False)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise Stop("UNSAFE_RUN_DIRECTORY")
    return path


def binaries(names):
    result = {}
    for name in names:
        p = shutil.which(name, path=TRUSTED_PATH + ":/usr/local/bin")
        if not p:
            raise Stop("MISSING_TOOL_" + name)
        result[name] = str(Path(p).resolve())
    return result


def source_files():
    return ["collect_preflight.py", "collect_api_precheck.py", "stageb_common.py",
            "stageb_observer.py", "stageb_injector.py", "stageb_agent.py"]


def preserve_source(folder, data):
    root = Path(__file__).resolve().parent
    actual = {n: sha(root / n) for n in source_files()}
    if actual != data.get("source_hashes"):
        raise Stop("RUNTIME_SOURCE_HASH_MISMATCH")
    for name in source_files():
        shutil.copyfile(root / name, folder / ("source_" + name))
    atomic(folder / "INPUTS.json", data)


def state(folder, status, **values):
    value = dict(status=status, updated=stamp(), monotonic=time.monotonic(), **values)
    atomic(folder / "STATE.json", value)
    with (folder / "EVENTS.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")
    return value


def status(folder):
    value = read(folder / "STATE.json")
    value["age_seconds"] = time.monotonic() - value["monotonic"]
    return value


def lock(path):
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise Stop("ANOTHER_STAGEB_PROCESS_IS_RUNNING")
    return fd


def lease(folder, run_id, sequence):
    """Called on LB only after controller validates a NEW CP sample; never renew duplicates."""
    fd = lock(folder / "LEASE.lock")
    try:
        path = folder / "LEASE.json"
        previous = read(path) if path.exists() else {"sequence": 0}
        if type(sequence) is not int or sequence <= previous["sequence"]:
            raise Stop("OBSERVER_SEQUENCE_REPLAY")
        atomic(path, {"run_id": run_id, "sequence": sequence, "received_monotonic": time.monotonic(), "received": stamp()})
    finally:
        os.close(fd)


def require_lease(folder, run_id, now=None):
    now = time.monotonic() if now is None else now
    value = read(folder / "LEASE.json")
    age = now - value["received_monotonic"]
    if value["run_id"] != run_id or not 0 <= age <= LEASE_SECONDS:
        raise Stop("API_LEASE_EXPIRED_OR_INVALID")
    return value


class RuntimeRunner:
    """Shorter LB command bounds; no shell. Every command gets an original output pair."""
    def __init__(self, folder, tools, seconds=2):
        self.folder, self.tools, self.seconds, self.records = folder, tools, seconds, []

    def run(self, name, args, privileged=False, input_bytes=None):
        command = [self.tools[args[0]], *args[1:]]
        if privileged:
            command = [self.tools["sudo"], "-n", "--", self.tools["env"], "-i",
                       "PATH=" + TRUSTED_PATH, "LC_ALL=C", "LANG=C", self.tools["timeout"],
                       "--signal=TERM", "--kill-after=1s", str(self.seconds) + "s", *command]
        record = dict(name=name, argv=command, privileged=privileged, started=stamp(),
                      stdin=input_bytes.decode("ascii") if input_bytes else None,
                      return_code=None, outer_timeout=False)
        start = time.monotonic()
        outpath, errpath = self.folder / (name + ".stdout.txt"), self.folder / (name + ".stderr.txt")
        with outpath.open("xb") as out, errpath.open("xb") as err:
            try:
                proc = subprocess.run(command, input=input_bytes or b"", stdout=out, stderr=err,
                                      env=ENV, timeout=self.seconds + 2, check=False)
                record["return_code"] = proc.returncode
            except subprocess.TimeoutExpired:
                record["outer_timeout"] = True
            except OSError as exc:
                record["execution_error"] = str(exc)
            finally:
                record.update(finished=stamp(), elapsed_seconds=time.monotonic() - start)
                self.records.append(record)
                atomic(self.folder / "COMMANDS.json", self.records)
        return dict(record, stdout=outpath.read_text(errors="replace"), stderr=errpath.read_text(errors="replace"))
