#!/usr/bin/env bash

set -uo pipefail

LB_IP="${LB_IP:-10.1.93.109}"
LB_PORT="${LB_PORT:-6443}"
LB_INTERFACE="${LB_INTERFACE:-ens160}"
EVIDENCE_DIR="${EVIDENCE_DIR:-/var/log/fds-evidence/P1-LB-01/stage-a}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/fds/P1-LB-01}"
HAPROXY_STATS_SOCKET="${HAPROXY_STATS_SOCKET:-}"

NODE_SOURCES=(
  "10.1.93.102/32"
  "10.1.93.103/32"
  "10.1.93.104/32"
  "10.1.93.105/32"
  "10.1.93.107/32"
  "10.1.93.108/32"
)
RUNNER_SOURCE="10.250.10.20/32"
MONITOR_SOURCE="10.250.10.30/32"
BACKENDS=("10.1.93.102" "10.1.93.103" "10.1.93.104")

usage() {
  cat <<'USAGE'
Usage:
  ./p1-lb-01-stage-a-lb.sh precheck
  IF11A_APPROVED=YES ./p1-lb-01-stage-a-lb.sh apply-firewall
  ./p1-lb-01-stage-a-lb.sh collect
  EVIDENCE_PERMISSION_APPROVED=YES ./p1-lb-01-stage-a-lb.sh normalize-evidence
  ./p1-lb-01-stage-a-lb.sh finalize

Optional environment variables:
  LB_INTERFACE=ens160
  LB_ZONE=public
  BRIDGED_CONNECTION=<NetworkManager connection name>
  EVIDENCE_DIR=/var/log/fds-evidence/P1-LB-01/stage-a
  HAPROXY_STATS_SOCKET=/var/lib/haproxy/stats

apply-firewall requires confirmation of D35's documented IF-11A approval.
Setting IF11A_APPROVED=YES is an execution guard, not a new approval record.
USAGE
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $1" >&2
    exit 2
  }
}

resolve_context() {
  require_command firewall-cmd
  require_command nmcli

  if [[ -z "${LB_ZONE:-}" ]]; then
    LB_ZONE="$(sudo firewall-cmd --get-zone-of-interface="$LB_INTERFACE" 2>/dev/null || true)"
  fi
  if [[ -z "$LB_ZONE" || "$LB_ZONE" == "no zone" ]]; then
    echo "ERROR: firewalld zone for $LB_INTERFACE could not be resolved." >&2
    echo "Set LB_ZONE explicitly after checking: firewall-cmd --get-active-zones" >&2
    exit 2
  fi

  if [[ -z "${BRIDGED_CONNECTION:-}" ]]; then
    BRIDGED_CONNECTION="$(nmcli -g GENERAL.CONNECTION device show "$LB_INTERFACE" 2>/dev/null || true)"
  fi
  if [[ -z "$BRIDGED_CONNECTION" || "$BRIDGED_CONNECTION" == "--" ]]; then
    echo "ERROR: active NetworkManager connection for $LB_INTERFACE could not be resolved." >&2
    echo "Set BRIDGED_CONNECTION explicitly after checking nmcli device status." >&2
    exit 2
  fi
}

resolve_stats_socket() {
  local configured_socket=""

  if [[ -z "$HAPROXY_STATS_SOCKET" ]]; then
    configured_socket="$(sudo awk '$1 == "stats" && $2 == "socket" {print $3; exit}' /etc/haproxy/haproxy.cfg 2>/dev/null || true)"
    if [[ -n "$configured_socket" ]] && sudo test -S "$configured_socket"; then
      HAPROXY_STATS_SOCKET="$configured_socket"
    elif sudo test -S /var/lib/haproxy/stats; then
      HAPROXY_STATS_SOCKET="/var/lib/haproxy/stats"
    elif sudo test -S /run/haproxy/admin.sock; then
      HAPROXY_STATS_SOCKET="/run/haproxy/admin.sock"
    fi
  fi

  if [[ -z "$HAPROXY_STATS_SOCKET" ]] || ! sudo test -S "$HAPROXY_STATS_SOCKET"; then
    echo "ERROR: HAProxy stats socket could not be resolved." >&2
    echo "Check the 'stats socket' directive and set HAPROXY_STATS_SOCKET explicitly." >&2
    exit 2
  fi
}

rule_for_source() {
  local source="$1"
  printf 'rule family="ipv4" source address="%s" port port="%s" protocol="tcp" accept' \
    "$source" "$LB_PORT"
}

precheck() {
  resolve_context
  resolve_stats_socket
  echo "timestamp=$(date --iso-8601=seconds)"
  echo "lb_ip=$LB_IP"
  echo "lb_interface=$LB_INTERFACE"
  echo "lb_zone=$LB_ZONE"
  echo "bridged_connection=$BRIDGED_CONNECTION"
  echo "haproxy_stats_socket=$HAPROXY_STATS_SOCKET"
  echo
  hostnamectl --static
  ip -br address show dev "$LB_INTERFACE"
  ip route
  sudo systemctl is-enabled firewalld
  sudo systemctl is-active firewalld
  sudo firewall-cmd --get-active-zones
  sudo firewall-cmd --zone="$LB_ZONE" --list-all
  sudo systemctl is-enabled haproxy
  sudo systemctl is-active haproxy
  sudo ss -lntp | grep -F "$LB_IP:$LB_PORT" || true
  getenforce
  getsebool haproxy_connect_any
}

apply_firewall() {
  resolve_context

  if [[ "${IF11A_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: IF-11A approval guard is not set." >&2
    echo "After confirming the D35 approval record, rerun with IF11A_APPROVED=YES." >&2
    exit 3
  fi

  if [[ "$(sudo systemctl is-active firewalld 2>/dev/null || true)" != "active" ]]; then
    echo "ERROR: firewalld is not active on the API LB." >&2
    exit 3
  fi

  sudo install -d -m 0750 "$BACKUP_DIR"
  local backup_file="$BACKUP_DIR/firewalld-rich-rules.before-if11a.$(date +%Y%m%dT%H%M%S%z).txt"
  sudo firewall-cmd --permanent --zone="$LB_ZONE" --list-rich-rules | sudo tee "$backup_file" >/dev/null
  echo "Saved pre-change rules: $backup_file"

  local sources=("$RUNNER_SOURCE" "$MONITOR_SOURCE" "${NODE_SOURCES[@]}")
  local source rule
  for source in "${sources[@]}"; do
    rule="$(rule_for_source "$source")"
    if sudo firewall-cmd --permanent --zone="$LB_ZONE" --query-rich-rule="$rule" >/dev/null 2>&1; then
      echo "EXISTS: $source -> $LB_IP:$LB_PORT/tcp"
    else
      sudo firewall-cmd --permanent --zone="$LB_ZONE" --add-rich-rule="$rule"
      echo "ADDED:  $source -> $LB_IP:$LB_PORT/tcp"
    fi
  done

  sudo firewall-cmd --reload

  if sudo firewall-cmd --zone="$LB_ZONE" --query-port="$LB_PORT/tcp" >/dev/null 2>&1; then
    echo "ERROR: $LB_PORT/tcp is open as a zone-wide port. Remove the broad port only after confirming ownership." >&2
    exit 4
  fi

  echo "Runtime rich rules after reload:"
  sudo firewall-cmd --zone="$LB_ZONE" --list-rich-rules
}

collect() {
  local config_file="/etc/haproxy/haproxy.cfg"
  local config_output config_rc
  resolve_context
  resolve_stats_socket
  require_command haproxy
  require_command nc
  require_command socat
  umask 027

  sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" "$EVIDENCE_DIR"

  sudo hostnamectl > "$EVIDENCE_DIR/01_hostnamectl.txt"
  sudo ip -br address > "$EVIDENCE_DIR/02_ip_address.txt"
  sudo ip route > "$EVIDENCE_DIR/03_ip_route.txt"
  sudo nmcli connection show "$BRIDGED_CONNECTION" > "$EVIDENCE_DIR/04_nmcli_connection.txt"
  sudo haproxy -vv > "$EVIDENCE_DIR/05_haproxy_version.txt" 2>&1
  config_output="$(sudo haproxy -c -f "$config_file" 2>&1)"
  config_rc=$?
  {
    echo "test=P1-LB-01 Stage A HAProxy configuration validation"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "source_host=$(hostnamectl --static)"
    echo "command=haproxy -c -f $config_file"
    echo "exit_code=$config_rc"
    if [[ -n "$config_output" ]]; then
      printf '%s\n' "$config_output"
    else
      echo "output=(no output returned by haproxy)"
    fi
    if [[ $config_rc -eq 0 ]]; then
      echo "verdict=PASS"
    else
      echo "verdict=FAIL"
    fi
  } > "$EVIDENCE_DIR/06_haproxy_config_check.txt"
  if [[ $config_rc -ne 0 ]]; then
    echo "ERROR: HAProxy configuration validation failed; collection stopped." >&2
    exit 5
  fi
  sudo cp -a "$config_file" "$EVIDENCE_DIR/07_haproxy.cfg"
  sudo systemctl --no-pager --full status haproxy > "$EVIDENCE_DIR/08_haproxy_status.txt" 2>&1
  sudo ss -lntp > "$EVIDENCE_DIR/09_listener.txt"
  sudo firewall-cmd --zone="$LB_ZONE" --list-all > "$EVIDENCE_DIR/10_firewalld.txt"
  sudo getsebool haproxy_connect_any > "$EVIDENCE_DIR/11_selinux_boolean.txt"
  sudo ausearch -m AVC,USER_AVC -ts recent > "$EVIDENCE_DIR/12_selinux_avc.txt" 2>&1 || true
  echo 'show stat' | sudo socat stdio "UNIX-CONNECT:$HAPROXY_STATS_SOCKET" > "$EVIDENCE_DIR/13_haproxy_stats.csv"
  sudo journalctl -u haproxy -b --no-pager > "$EVIDENCE_DIR/14_haproxy_journal.txt"

  local backend_file="$EVIDENCE_DIR/15_backend_prebootstrap_test.txt"
  local backend result rc backend_fail=0
  {
    echo "test=P1-LB-01 Stage A LB-to-CP pre-bootstrap"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "source_host=$(hostnamectl --static)"
    echo "source_ip=$LB_IP"
    echo
  } > "$backend_file"

  for backend in "${BACKENDS[@]}"; do
    result="$(nc -zv -w 2 "$backend" "$LB_PORT" 2>&1)"
    rc=$?
    {
      echo "command=nc -zv -w 2 $backend $LB_PORT"
      echo "exit_code=$rc"
      echo "$result"
    } >> "$backend_file"

    if grep -qi 'Connection refused' <<<"$result"; then
      echo "verdict=PASS_ROUTE_API_NOT_STARTED" >> "$backend_file"
    elif [[ $rc -eq 0 ]]; then
      echo "verdict=REVIEW_UNEXPECTED_LISTENER" >> "$backend_file"
      backend_fail=1
    else
      echo "verdict=FAIL_ROUTE_OR_FIREWALL" >> "$backend_file"
      backend_fail=1
    fi
    echo >> "$backend_file"
  done

  echo "Evidence 01-15 collected in: $EVIDENCE_DIR"
  sudo chmod 0640 "$EVIDENCE_DIR"/{01_hostnamectl.txt,02_ip_address.txt,03_ip_route.txt,04_nmcli_connection.txt,05_haproxy_version.txt,06_haproxy_config_check.txt,07_haproxy.cfg,08_haproxy_status.txt,09_listener.txt,10_firewalld.txt,11_selinux_boolean.txt,12_selinux_avc.txt,13_haproxy_stats.csv,14_haproxy_journal.txt,15_backend_prebootstrap_test.txt}
  if [[ $backend_fail -ne 0 ]]; then
    echo "ERROR: at least one backend requires review; inspect $backend_file" >&2
    exit 6
  fi
  echo "LB-to-CP pre-bootstrap verdict: PASS"
}

normalize_evidence() {
  if [[ "${EVIDENCE_PERMISSION_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: Evidence permission normalization guard is not set." >&2
    exit 7
  fi
  if [[ ! -d "$EVIDENCE_DIR" ]]; then
    echo "ERROR: Evidence directory not found: $EVIDENCE_DIR" >&2
    exit 7
  fi
  sudo find "$EVIDENCE_DIR" -maxdepth 1 -type f -exec chmod 0640 -- {} +
  echo "Evidence file modes normalized to 0640: $EVIDENCE_DIR"
}

finalize() {
  local required=(
    01_hostnamectl.txt
    02_ip_address.txt
    03_ip_route.txt
    04_nmcli_connection.txt
    05_haproxy_version.txt
    06_haproxy_config_check.txt
    07_haproxy.cfg
    08_haproxy_status.txt
    09_listener.txt
    10_firewalld.txt
    11_selinux_boolean.txt
    12_selinux_avc.txt
    13_haproxy_stats.csv
    14_haproxy_journal.txt
    15_backend_prebootstrap_test.txt
    16_positive_test_nodes.txt
    17_positive_test_runner.txt
    18_negative_test.txt
    18a_secure_evidence_transfer_control.txt
    18b_secure_transfer_ansible_client.txt
    18c_secure_transfer_runner_client.txt
    19_stage_a_handoff_review.md
  )
  local missing=0 file mode manifest_tmp
  for file in "${required[@]}"; do
    if [[ ! -s "$EVIDENCE_DIR/$file" ]]; then
      echo "MISSING_OR_EMPTY: $EVIDENCE_DIR/$file" >&2
      missing=1
      continue
    fi
    if [[ -L "$EVIDENCE_DIR/$file" ]]; then
      echo "SYMLINK_NOT_ALLOWED: $EVIDENCE_DIR/$file" >&2
      missing=1
      continue
    fi
    mode="$(sudo stat -c '%a' "$EVIDENCE_DIR/$file")"
    if [[ "$mode" != "640" ]]; then
      echo "INVALID_MODE_${mode}: $EVIDENCE_DIR/$file (expected 640)" >&2
      missing=1
    fi
  done
  if [[ $missing -ne 0 ]]; then
    echo "ERROR: Evidence set is incomplete. SHA256 manifest was not regenerated." >&2
    exit 6
  fi

  manifest_tmp="$(mktemp)"
  (
    cd "$EVIDENCE_DIR" || exit 1
    find . -maxdepth 1 -type f ! -name '99_SHA256SUMS.txt' -printf '%f\n' \
      | LC_ALL=C sort \
      | xargs -r sha256sum
  ) > "$manifest_tmp"
  sudo install -m 0640 "$manifest_tmp" "$EVIDENCE_DIR/99_SHA256SUMS.txt"
  rm -f -- "$manifest_tmp"

  (
    cd "$EVIDENCE_DIR" || exit 1
    sha256sum -c 99_SHA256SUMS.txt
  )

  echo "Evidence set finalized: $EVIDENCE_DIR"
  echo "Next: copy it to docs/evidence/P1-LB-01/stage-a/ and record the Git commit ID."
}

mode="${1:-}"
case "$mode" in
  precheck) precheck ;;
  apply-firewall) apply_firewall ;;
  collect) collect ;;
  normalize-evidence) normalize_evidence ;;
  finalize) finalize ;;
  *) usage; exit 1 ;;
esac
