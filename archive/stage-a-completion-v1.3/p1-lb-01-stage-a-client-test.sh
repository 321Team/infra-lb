#!/usr/bin/env bash

set -uo pipefail

LB_IP="${LB_IP:-10.1.93.109}"
LB_PORT="${LB_PORT:-6443}"
MODE="${1:-}"
OUTPUT_FILE="${2:-}"
ALLOWED_NODE_IPS=("10.1.93.102" "10.1.93.103" "10.1.93.104" "10.1.93.105" "10.1.93.107" "10.1.93.108")
RUNNER_IP="10.250.10.20"
MONITOR_IP="10.250.10.30"

usage() {
  cat <<'USAGE'
Usage:
  ./p1-lb-01-stage-a-client-test.sh positive-node [output-file]
  ./p1-lb-01-stage-a-client-test.sh positive-runner [output-file]
  ./p1-lb-01-stage-a-client-test.sh negative [output-file]

Defaults:
  positive-node   /tmp/16_positive_test_node_<hostname>.txt
  positive-runner /tmp/17_positive_test_runner.txt
  negative        /tmp/18_negative_test.txt
USAGE
}

contains() {
  local expected="$1" item
  shift
  for item in "$@"; do
    [[ "$item" == "$expected" ]] && return 0
  done
  return 1
}

command -v nc >/dev/null 2>&1 || {
  echo "ERROR: nc is required. On CentOS Stream 10 it is provided by nmap-ncat." >&2
  exit 2
}

case "$MODE" in
  positive-node)
    OUTPUT_FILE="${OUTPUT_FILE:-/tmp/16_positive_test_node_$(hostnamectl --static).txt}"
    ;;
  positive-runner)
    OUTPUT_FILE="${OUTPUT_FILE:-/tmp/17_positive_test_runner.txt}"
    ;;
  negative)
    OUTPUT_FILE="${OUTPUT_FILE:-/tmp/18_negative_test.txt}"
    ;;
  *)
    usage
    exit 1
    ;;
esac

route_output="$(ip route get "$LB_IP" 2>&1)"
source_ip="$(awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' <<<"$route_output")"

if [[ -z "$source_ip" ]]; then
  echo "ERROR: source IP could not be determined from: $route_output" >&2
  exit 3
fi

source_check="PASS"
case "$MODE" in
  positive-node)
    contains "$source_ip" "${ALLOWED_NODE_IPS[@]}" || source_check="FAIL_NOT_APPROVED_NODE_SOURCE"
    ;;
  positive-runner)
    [[ "$source_ip" == "$RUNNER_IP" ]] || source_check="FAIL_NOT_RUNNER_SOURCE"
    ;;
  negative)
    if contains "$source_ip" "${ALLOWED_NODE_IPS[@]}" || [[ "$source_ip" == "$RUNNER_IP" || "$source_ip" == "$MONITOR_IP" ]]; then
      source_check="FAIL_SOURCE_IS_IN_ALLOWLIST"
    fi
    ;;
esac

nc_output="$(nc -zv -w 2 "$LB_IP" "$LB_PORT" 2>&1)"
nc_rc=$?

case "$MODE" in
  positive-node|positive-runner)
    if [[ "$source_check" == "PASS" && $nc_rc -eq 0 ]]; then
      verdict="PASS"
      final_rc=0
    else
      verdict="FAIL"
      final_rc=4
    fi
    ;;
  negative)
    if [[ "$source_check" == "PASS" && $nc_rc -ne 0 ]]; then
      verdict="PASS_BLOCKED"
      final_rc=0
    else
      verdict="FAIL_UNAPPROVED_SOURCE_REACHED_LISTENER"
      final_rc=5
    fi
    ;;
esac

{
  echo "test=P1-LB-01 Stage A $MODE"
  echo "timestamp=$(date --iso-8601=seconds)"
  echo "source_host=$(hostnamectl --static)"
  echo "source_ip=$source_ip"
  echo "source_check=$source_check"
  echo "route=$route_output"
  echo "command=nc -zv -w 2 $LB_IP $LB_PORT"
  echo "exit_code=$nc_rc"
  echo "$nc_output"
  echo "verdict=$verdict"
} | tee "$OUTPUT_FILE"

echo "Evidence saved: $OUTPUT_FILE"
exit "$final_rc"
