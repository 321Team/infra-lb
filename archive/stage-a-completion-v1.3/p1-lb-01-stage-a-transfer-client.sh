#!/usr/bin/env bash

set -uo pipefail

LB_IP="${LB_IP:-10.1.93.109}"
LB_USER="${LB_USER:-server01_k8s-api-lb}"
STATE_DIR="${STATE_DIR:-${HOME}/.local/state/p1-lb-01-stage-a-transfer}"
KNOWN_HOSTS_FILE="${KNOWN_HOSTS_FILE:-${HOME}/.ssh/known_hosts_p1_lb_01}"

usage() {
  cat <<'USAGE'
Usage:
  ./p1-lb-01-stage-a-transfer-client.sh prepare <ansible|runner>
  ./p1-lb-01-stage-a-transfer-client.sh pin-host-key <expected-SHA256-fingerprint>
  ./p1-lb-01-stage-a-transfer-client.sh export-control-evidence <ansible|runner>
  ./p1-lb-01-stage-a-transfer-client.sh send <ansible|runner> <evidence-file> <expected-sha256>
  TRANSFER_REVOKE_APPROVED=YES ./p1-lb-01-stage-a-transfer-client.sh revoke-local <ansible|runner>

Policy:
  - password and keyboard-interactive authentication are disabled
  - only one explicit, passphrase-protected ephemeral key is offered
  - the LB ED25519 host key must match the console-confirmed fingerprint
  - the server-side forced command accepts only approved Evidence filenames
USAGE
}

role_values() {
  local role="$1"
  case "$role" in
    ansible)
      EXPECTED_SOURCE="10.250.10.10"
      KEY_FILE="${HOME}/.ssh/p1-lb-01-stage-a-ansible-ed25519"
      KEY_TAG="p1-lb-01-stage-a-ansible-20260903"
      ;;
    runner)
      EXPECTED_SOURCE="10.250.10.20"
      KEY_FILE="${HOME}/.ssh/p1-lb-01-stage-a-runner-ed25519"
      KEY_TAG="p1-lb-01-stage-a-runner-20260903"
      ;;
    *)
      echo "ERROR: role must be ansible or runner" >&2
      exit 2
      ;;
  esac
}

ensure_dirs() {
  umask 077
  install -d -m 0700 "${HOME}/.ssh" "$STATE_DIR"
}

ssh_options() {
  SSH_OPTIONS=(
    -o IdentityAgent=none
    -o IdentitiesOnly=yes
    -o PreferredAuthentications=publickey
    -o PasswordAuthentication=no
    -o KbdInteractiveAuthentication=no
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile="$KNOWN_HOSTS_FILE"
    -i "$KEY_FILE"
  )
}

prepare() {
  local role="$1"
  role_values "$role"
  ensure_dirs

  if [[ -e "$KEY_FILE" || -e "$KEY_FILE.pub" ]]; then
    echo "ERROR: key already exists; do not overwrite: $KEY_FILE" >&2
    exit 3
  fi

  echo "Create a non-empty passphrase when prompted."
  ssh-keygen -t ed25519 -a 100 -f "$KEY_FILE" -C "$KEY_TAG"
  if ssh-keygen -y -P '' -f "$KEY_FILE" >/dev/null 2>&1; then
    rm -f -- "$KEY_FILE" "$KEY_FILE.pub"
    echo "ERROR: an empty passphrase is not permitted; generated key was removed" >&2
    exit 3
  fi
  chmod 0600 "$KEY_FILE"
  chmod 0644 "$KEY_FILE.pub"

  fingerprint="$(ssh-keygen -lf "$KEY_FILE.pub" -E sha256 | awk '{print $2}')"
  {
    echo "test=P1-LB-01 Stage A ephemeral transfer key preparation"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "role=$role"
    echo "source_host=$(hostnamectl --static)"
    echo "expected_source_ip=$EXPECTED_SOURCE"
    echo "key_tag=$KEY_TAG"
    echo "key_fingerprint=$fingerprint"
    echo "private_key_mode=$(stat -c '%a' "$KEY_FILE")"
    echo "verdict=PASS"
  } > "$STATE_DIR/prepare_${role}.txt"
  chmod 0600 "$STATE_DIR/prepare_${role}.txt"

  echo "KEY_PREPARED role=$role fingerprint=$fingerprint"
  echo "Provide the following PUBLIC key to the LB console authorization step:"
  cat "$KEY_FILE.pub"
}

pin_host_key() {
  local expected_fingerprint="$1"
  ensure_dirs

  if [[ ! "$expected_fingerprint" =~ ^SHA256:[A-Za-z0-9+/]+={0,2}$ ]]; then
    echo "ERROR: expected ED25519 fingerprint must use SHA256:<base64> format" >&2
    exit 4
  fi

  candidate="$(mktemp "$STATE_DIR/known_hosts_candidate.XXXXXX")"
  scan_log="$(mktemp "$STATE_DIR/ssh_keyscan.XXXXXX")"
  trap 'rm -f -- "$candidate" "$scan_log"' RETURN
  ssh-keyscan -T 5 -t ed25519 "$LB_IP" > "$candidate" 2> "$scan_log"
  if [[ ! -s "$candidate" ]]; then
    echo "ERROR: LB ED25519 host key scan returned no key" >&2
    exit 5
  fi

  actual_fingerprint="$(ssh-keygen -lf "$candidate" -E sha256 | awk 'NR == 1 {print $2}')"
  if [[ "$actual_fingerprint" != "$expected_fingerprint" ]]; then
    echo "ERROR: LB host key fingerprint mismatch" >&2
    echo "expected=$expected_fingerprint" >&2
    echo "actual=$actual_fingerprint" >&2
    exit 6
  fi

  install -m 0600 "$candidate" "$KNOWN_HOSTS_FILE"
  {
    echo "test=P1-LB-01 Stage A LB host key pinning"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "source_host=$(hostnamectl --static)"
    echo "lb_ip=$LB_IP"
    echo "algorithm=ED25519"
    echo "console_expected_fingerprint=$expected_fingerprint"
    echo "scanned_fingerprint=$actual_fingerprint"
    echo "known_hosts_file=$KNOWN_HOSTS_FILE"
    echo "known_hosts_mode=$(stat -c '%a' "$KNOWN_HOSTS_FILE")"
    echo "verdict=PASS"
  } > "$STATE_DIR/host_key_pinning.txt"
  chmod 0600 "$STATE_DIR/host_key_pinning.txt"
  rm -f -- "$candidate" "$scan_log"
  trap - RETURN
  echo "HOST_KEY_PINNED fingerprint=$actual_fingerprint"
}

send_file() {
  local role="$1" file="$2" expected_sha="$3"
  role_values "$role"
  ensure_dirs
  ssh_options

  if [[ ! -f "$file" || -L "$file" ]]; then
    echo "ERROR: Evidence must be a regular, non-symlink file: $file" >&2
    exit 7
  fi
  if [[ ! -f "$KEY_FILE" || ! -f "$KEY_FILE.pub" ]]; then
    echo "ERROR: approved ephemeral key is missing: $KEY_FILE" >&2
    exit 8
  fi
  if [[ ! -s "$KNOWN_HOSTS_FILE" || "$(stat -c '%a' "$KNOWN_HOSTS_FILE")" != "600" ]]; then
    echo "ERROR: pinned project known_hosts file is missing or not mode 600" >&2
    exit 9
  fi
  if [[ ! "$expected_sha" =~ ^[0-9a-f]{64}$ ]]; then
    echo "ERROR: expected SHA-256 is invalid" >&2
    exit 10
  fi

  filename="$(basename -- "$file")"
  case "$role:$filename" in
    ansible:16_positive_test_nodes.txt|ansible:18_negative_test.txt|ansible:18b_secure_transfer_ansible_client.txt) ;;
    runner:17_positive_test_runner.txt|runner:18c_secure_transfer_runner_client.txt) ;;
    *)
      echo "ERROR: Evidence filename is not approved for role=$role: $filename" >&2
      exit 11
      ;;
  esac

  actual_sha="$(sha256sum "$file" | awk '{print $1}')"
  if [[ "$actual_sha" != "$expected_sha" ]]; then
    echo "ERROR: local Evidence SHA-256 mismatch" >&2
    exit 12
  fi

  route_output="$(ip route get "$LB_IP" 2>&1)"
  source_ip="$(awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}' <<<"$route_output")"
  if [[ "$source_ip" != "$EXPECTED_SOURCE" ]]; then
    echo "ERROR: transfer source IP mismatch: expected=$EXPECTED_SOURCE actual=$source_ip" >&2
    exit 13
  fi

  transfer_output="$(ssh "${SSH_OPTIONS[@]}" "$LB_USER@$LB_IP" \
    "upload $filename $expected_sha" < "$file" 2>&1)"
  transfer_rc=$?

  {
    echo "test=P1-LB-01 Stage A policy-controlled Evidence transfer"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "role=$role"
    echo "source_host=$(hostnamectl --static)"
    echo "source_ip=$source_ip"
    echo "destination=$LB_IP"
    echo "authentication=publickey-only"
    echo "identities_only=yes"
    echo "identity_agent=none"
    echo "strict_host_key_checking=yes"
    echo "file=$filename"
    echo "sha256=$actual_sha"
    echo "exit_code=$transfer_rc"
    printf '%s\n' "$transfer_output"
    if [[ $transfer_rc -eq 0 && "$transfer_output" == UPLOAD_OK* ]]; then
      echo "verdict=PASS"
    else
      echo "verdict=FAIL"
    fi
  } > "$STATE_DIR/send_${filename}.txt"
  chmod 0600 "$STATE_DIR/send_${filename}.txt"

  printf '%s\n' "$transfer_output"
  if [[ $transfer_rc -ne 0 || "$transfer_output" != UPLOAD_OK* ]]; then
    echo "ERROR: controlled transfer failed" >&2
    exit 14
  fi
}

export_control_evidence() {
  local role="$1" output_file required_log
  role_values "$role"
  ensure_dirs

  for required_log in "prepare_${role}.txt" host_key_pinning.txt; do
    if [[ ! -s "$STATE_DIR/$required_log" ]]; then
      echo "ERROR: missing client control record: $STATE_DIR/$required_log" >&2
      exit 17
    fi
  done
  if [[ "$role" == "ansible" ]]; then
    for required_log in send_16_positive_test_nodes.txt.txt send_18_negative_test.txt.txt; do
      [[ -s "$STATE_DIR/$required_log" ]] || {
        echo "ERROR: missing client transfer record: $STATE_DIR/$required_log" >&2
        exit 18
      }
    done
    output_file="$STATE_DIR/18b_secure_transfer_ansible_client.txt"
  else
    required_log="send_17_positive_test_runner.txt.txt"
    [[ -s "$STATE_DIR/$required_log" ]] || {
      echo "ERROR: missing client transfer record: $STATE_DIR/$required_log" >&2
      exit 18
    }
    output_file="$STATE_DIR/18c_secure_transfer_runner_client.txt"
  fi

  {
    echo "test=P1-LB-01 Stage A secure transfer client control"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "role=$role"
    echo "source_host=$(hostnamectl --static)"
    echo "expected_source_ip=$EXPECTED_SOURCE"
    echo "client_script_sha256=$(sha256sum "$0" | awk '{print $1}')"
    echo "authentication=publickey-only"
    echo "password_authentication=disabled"
    echo "keyboard_interactive_authentication=disabled"
    echo "identity_agent=none"
    echo "identities_only=yes"
    echo "strict_host_key_checking=yes"
    echo "known_hosts_file=$KNOWN_HOSTS_FILE"
    echo "known_hosts_mode=$(stat -c '%a' "$KNOWN_HOSTS_FILE")"
    echo "===== KEY PREPARATION ====="
    cat "$STATE_DIR/prepare_${role}.txt"
    echo "===== HOST KEY PINNING ====="
    cat "$STATE_DIR/host_key_pinning.txt"
    echo "===== FILE TRANSFERS ====="
    if [[ "$role" == "ansible" ]]; then
      cat "$STATE_DIR/send_16_positive_test_nodes.txt.txt"
      cat "$STATE_DIR/send_18_negative_test.txt.txt"
    else
      cat "$STATE_DIR/send_17_positive_test_runner.txt.txt"
    fi
    echo "control_verdict=PASS"
  } > "$output_file"
  chmod 0600 "$output_file"
  echo "CONTROL_EVIDENCE_READY file=$output_file sha256=$(sha256sum "$output_file" | awk '{print $1}')"
}

revoke_local() {
  local role="$1"
  role_values "$role"
  ensure_dirs

  if [[ "${TRANSFER_REVOKE_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: local key revocation guard is not set" >&2
    exit 15
  fi
  if [[ ! -f "$KEY_FILE.pub" ]]; then
    echo "ERROR: public key is missing; fingerprint cannot be recorded before deletion" >&2
    exit 16
  fi

  fingerprint="$(ssh-keygen -lf "$KEY_FILE.pub" -E sha256 | awk '{print $2}')"
  {
    echo "test=P1-LB-01 Stage A local ephemeral key revocation"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "role=$role"
    echo "source_host=$(hostnamectl --static)"
    echo "key_tag=$KEY_TAG"
    echo "key_fingerprint=$fingerprint"
    echo "server_revocation_prerequisite=operator-confirmed"
    echo "verdict=PASS_REVOKED"
  } > "$STATE_DIR/revoke_local_${role}.txt"
  chmod 0600 "$STATE_DIR/revoke_local_${role}.txt"

  rm -f -- "$KEY_FILE" "$KEY_FILE.pub"
  echo "LOCAL_KEY_REVOKED role=$role fingerprint=$fingerprint"
}

mode="${1:-}"
case "$mode" in
  prepare)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    prepare "$2"
    ;;
  pin-host-key)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    pin_host_key "$2"
    ;;
  export-control-evidence)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    export_control_evidence "$2"
    ;;
  send)
    [[ $# -eq 4 ]] || { usage; exit 1; }
    send_file "$2" "$3" "$4"
    ;;
  revoke-local)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    revoke_local "$2"
    ;;
  *)
    usage
    exit 1
    ;;
esac
