#!/usr/bin/env bash

set -uo pipefail

EXPECTED_USER="${EXPECTED_USER:-server01_k8s-api-lb}"
EVIDENCE_DIR="${EVIDENCE_DIR:-/var/log/fds-evidence/P1-LB-01/stage-a}"
INBOX_DIR="${INBOX_DIR:-${HOME}/.p1-lb-01-evidence-inbox}"
STATE_DIR="${STATE_DIR:-${HOME}/.local/state/p1-lb-01-stage-a-transfer}"
RECEIVER_SOURCE="${RECEIVER_SOURCE:-$(cd -- "$(dirname -- "$0")" && pwd)/p1-lb-01-stage-a-evidence-receiver.sh}"
RECEIVER_TARGET="${HOME}/.local/bin/p1-lb-01-stage-a-evidence-receiver"
AUTHORIZED_KEYS="${HOME}/.ssh/authorized_keys"

usage() {
  cat <<'USAGE'
Usage:
  ./p1-lb-01-stage-a-transfer-lb.sh precheck
  TRANSFER_CONTROL_APPROVED=YES ./p1-lb-01-stage-a-transfer-lb.sh prepare
  TRANSFER_CONTROL_APPROVED=YES ./p1-lb-01-stage-a-transfer-lb.sh authorize <ansible|runner>
  ./p1-lb-01-stage-a-transfer-lb.sh merge <approved-file> <expected-sha256>
  TRANSFER_REVOKE_APPROVED=YES ./p1-lb-01-stage-a-transfer-lb.sh revoke-and-evidence

The authorize command reads one OpenSSH ED25519 PUBLIC key line from stdin.
Never paste a private key or passphrase.
USAGE
}

role_values() {
  local role="$1"
  case "$role" in
    ansible)
      EXPECTED_SOURCE="10.250.10.10"
      KEY_TAG="p1-lb-01-stage-a-ansible-20260903"
      ;;
    runner)
      EXPECTED_SOURCE="10.250.10.20"
      KEY_TAG="p1-lb-01-stage-a-runner-20260903"
      ;;
    *)
      echo "ERROR: role must be ansible or runner" >&2
      exit 2
      ;;
  esac
}

require_expected_user() {
  if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
    echo "ERROR: run as $EXPECTED_USER, not $(id -un)" >&2
    exit 3
  fi
}

backup_authorized_keys() {
  local reason="$1" backup_file
  install -d -m 0700 "$STATE_DIR/backups"
  backup_file="$STATE_DIR/backups/authorized_keys.${reason}.$(date +%Y%m%dT%H%M%S%z)"
  if [[ -f "$AUTHORIZED_KEYS" ]]; then
    install -m 0600 "$AUTHORIZED_KEYS" "$backup_file"
  else
    : > "$backup_file"
    chmod 0600 "$backup_file"
  fi
  printf '%s' "$backup_file"
}

host_key_fingerprint() {
  sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
}

precheck() {
  require_expected_user
  echo "timestamp=$(date --iso-8601=seconds)"
  echo "host=$(hostnamectl --static)"
  echo "user=$(id -un)"
  echo "home=$HOME"
  echo "sshd_active=$(systemctl is-active sshd)"
  echo "receiver_source=$RECEIVER_SOURCE"
  echo "===== LB ED25519 HOST KEY FINGERPRINT ====="
  host_key_fingerprint
  echo "===== EXISTING TRANSFER KEY TAGS ====="
  if [[ -f "$AUTHORIZED_KEYS" ]]; then
    grep -F 'p1-lb-01-stage-a-' "$AUTHORIZED_KEYS" || true
  fi
}

prepare() {
  require_expected_user
  if [[ "${TRANSFER_CONTROL_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: transfer control approval guard is not set" >&2
    exit 4
  fi
  if [[ ! -f "$RECEIVER_SOURCE" ]]; then
    echo "ERROR: receiver script not found: $RECEIVER_SOURCE" >&2
    exit 5
  fi

  umask 077
  install -d -m 0700 "${HOME}/.ssh" "${HOME}/.local/bin" "$STATE_DIR" "$INBOX_DIR"
  touch "$AUTHORIZED_KEYS"
  chmod 0600 "$AUTHORIZED_KEYS"
  install -m 0700 "$RECEIVER_SOURCE" "$RECEIVER_TARGET"
  if command -v restorecon >/dev/null 2>&1; then
    restorecon -RF "${HOME}/.ssh" "${HOME}/.local" "$INBOX_DIR" >/dev/null 2>&1 || true
  fi

  {
    echo "test=P1-LB-01 Stage A secure Evidence receiver preparation"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "host=$(hostnamectl --static)"
    echo "user=$(id -un)"
    echo "authentication=publickey-only"
    echo "receiver=$RECEIVER_TARGET"
    echo "receiver_mode=$(stat -c '%a' "$RECEIVER_TARGET")"
    echo "inbox=$INBOX_DIR"
    echo "inbox_mode=$(stat -c '%a' "$INBOX_DIR")"
    echo "authorized_keys_mode=$(stat -c '%a' "$AUTHORIZED_KEYS")"
    echo "verdict=PASS"
  } > "$STATE_DIR/prepare_lb.txt"
  chmod 0600 "$STATE_DIR/prepare_lb.txt"
  echo "TRANSFER_RECEIVER_PREPARED"
}

authorize() {
  local role="$1" public_key fingerprint backup_file forced_command restricted_line
  require_expected_user
  role_values "$role"
  if [[ "${TRANSFER_CONTROL_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: transfer control approval guard is not set" >&2
    exit 6
  fi
  if [[ ! -x "$RECEIVER_TARGET" || ! -d "$INBOX_DIR" ]]; then
    echo "ERROR: run the prepare mode first" >&2
    exit 7
  fi
  if grep -Fq "$KEY_TAG" "$AUTHORIZED_KEYS"; then
    echo "ERROR: transfer key tag already exists: $KEY_TAG" >&2
    exit 8
  fi

  echo "Paste the $role PUBLIC key line, then press Enter:" >&2
  IFS= read -r public_key
  if [[ ! "$public_key" =~ ^ssh-ed25519[[:space:]]+[A-Za-z0-9+/=]+[[:space:]]+${KEY_TAG}$ ]]; then
    echo "ERROR: invalid ED25519 public key or unexpected key tag" >&2
    exit 9
  fi

  tmp_public="$(mktemp "$STATE_DIR/public_key.${role}.XXXXXX")"
  printf '%s\n' "$public_key" > "$tmp_public"
  chmod 0600 "$tmp_public"
  fingerprint="$(ssh-keygen -lf "$tmp_public" -E sha256 | awk '{print $2}')"
  rm -f -- "$tmp_public"

  backup_file="$(backup_authorized_keys "before-${role}-authorize")"
  forced_command="$RECEIVER_TARGET $role"
  restricted_line="from=\"$EXPECTED_SOURCE\",restrict,command=\"$forced_command\" $public_key"
  printf '%s\n' "$restricted_line" >> "$AUTHORIZED_KEYS"
  chmod 0600 "$AUTHORIZED_KEYS"
  if command -v restorecon >/dev/null 2>&1; then
    restorecon -F "$AUTHORIZED_KEYS" >/dev/null 2>&1 || true
  fi

  {
    echo "test=P1-LB-01 Stage A ephemeral transfer key authorization"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "role=$role"
    echo "allowed_source=$EXPECTED_SOURCE"
    echo "key_tag=$KEY_TAG"
    echo "key_fingerprint=$fingerprint"
    echo "restrictions=from,restrict,forced-command"
    echo "password_authentication=not-used"
    echo "authorized_keys_backup=$backup_file"
    echo "authorized_keys_backup_sha256=$(sha256sum "$backup_file" | awk '{print $1}')"
    echo "verdict=PASS_AUTHORIZED"
  } > "$STATE_DIR/authorize_${role}.txt"
  chmod 0600 "$STATE_DIR/authorize_${role}.txt"
  echo "TRANSFER_KEY_AUTHORIZED role=$role source=$EXPECTED_SOURCE fingerprint=$fingerprint"
}

validate_evidence_content() {
  local filename="$1" file="$2"
  case "$filename" in
    16_positive_test_nodes.txt)
      [[ "$(grep -c '^inventory_host=' "$file")" -eq 6 ]] || return 1
      [[ "$(grep -c '^verdict=PASS$' "$file")" -eq 6 ]] || return 1
      [[ "$(grep -c '^verdict=FAIL$' "$file")" -eq 0 ]] || return 1
      ;;
    17_positive_test_runner.txt)
      grep -Fxq 'source_ip=10.250.10.20' "$file" || return 1
      grep -Fxq 'exit_code=0' "$file" || return 1
      grep -Fxq 'verdict=PASS' "$file" || return 1
      ;;
    18_negative_test.txt)
      grep -Fxq 'source_ip=10.250.10.10' "$file" || return 1
      grep -Fxq 'exit_code=1' "$file" || return 1
      grep -Fxq 'verdict=PASS_BLOCKED' "$file" || return 1
      ;;
    18b_secure_transfer_ansible_client.txt)
      grep -Fxq 'role=ansible' "$file" || return 1
      grep -Fxq 'expected_source_ip=10.250.10.10' "$file" || return 1
      grep -Fxq 'authentication=publickey-only' "$file" || return 1
      grep -Fxq 'password_authentication=disabled' "$file" || return 1
      grep -Fxq 'strict_host_key_checking=yes' "$file" || return 1
      grep -Fxq 'control_verdict=PASS' "$file" || return 1
      ;;
    18c_secure_transfer_runner_client.txt)
      grep -Fxq 'role=runner' "$file" || return 1
      grep -Fxq 'expected_source_ip=10.250.10.20' "$file" || return 1
      grep -Fxq 'authentication=publickey-only' "$file" || return 1
      grep -Fxq 'password_authentication=disabled' "$file" || return 1
      grep -Fxq 'strict_host_key_checking=yes' "$file" || return 1
      grep -Fxq 'control_verdict=PASS' "$file" || return 1
      ;;
    *) return 1 ;;
  esac
}

merge_file() {
  local filename="$1" expected_sha="$2" source_file destination_file actual_sha
  require_expected_user
  case "$filename" in
    16_positive_test_nodes.txt|17_positive_test_runner.txt|18_negative_test.txt|18b_secure_transfer_ansible_client.txt|18c_secure_transfer_runner_client.txt) ;;
    *) echo "ERROR: unapproved Evidence filename: $filename" >&2; exit 10 ;;
  esac
  if [[ ! "$expected_sha" =~ ^[0-9a-f]{64}$ ]]; then
    echo "ERROR: expected SHA-256 is invalid" >&2
    exit 11
  fi

  source_file="$INBOX_DIR/$filename"
  destination_file="$EVIDENCE_DIR/$filename"
  if [[ ! -f "$source_file" || -L "$source_file" ]]; then
    echo "ERROR: protected inbox file missing or unsafe: $source_file" >&2
    exit 12
  fi
  actual_sha="$(sha256sum "$source_file" | awk '{print $1}')"
  if [[ "$actual_sha" != "$expected_sha" ]]; then
    echo "ERROR: protected inbox SHA-256 mismatch for $filename" >&2
    exit 13
  fi
  if ! validate_evidence_content "$filename" "$source_file"; then
    echo "ERROR: Evidence semantic validation failed for $filename" >&2
    exit 14
  fi

  sudo install -d -m 0750 "$EVIDENCE_DIR"
  sudo install -m 0640 "$source_file" "$destination_file"
  sudo sha256sum "$destination_file"
  sudo stat -c 'file=%n size=%s owner=%U group=%G mode=%a' "$destination_file"

  {
    echo "test=P1-LB-01 Stage A Evidence protected merge"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "file=$filename"
    echo "sha256=$actual_sha"
    echo "semantic_validation=PASS"
    echo "destination_mode=$(sudo stat -c '%a' "$destination_file")"
    echo "verdict=PASS_MERGED"
  } > "$STATE_DIR/merge_${filename}.txt"
  chmod 0600 "$STATE_DIR/merge_${filename}.txt"
}

revoke_and_evidence() {
  require_expected_user
  if [[ "${TRANSFER_REVOKE_APPROVED:-NO}" != "YES" ]]; then
    echo "ERROR: transfer key revocation guard is not set" >&2
    exit 15
  fi

  local required_state role tag backup_file tmp_auth auth_log ansible_log_count runner_log_count
  for required_state in \
    authorize_ansible.txt authorize_runner.txt \
    merge_16_positive_test_nodes.txt.txt \
    merge_17_positive_test_runner.txt.txt \
    merge_18_negative_test.txt.txt \
    merge_18b_secure_transfer_ansible_client.txt.txt \
    merge_18c_secure_transfer_runner_client.txt.txt; do
    if [[ ! -s "$STATE_DIR/$required_state" ]]; then
      echo "ERROR: missing transfer state: $STATE_DIR/$required_state" >&2
      exit 16
    fi
  done

  auth_log="$(sudo journalctl -u sshd -b --no-pager 2>/dev/null || true)"
  ansible_log_count="$(grep -Ec "Accepted publickey for ${EXPECTED_USER} from 10[.]250[.]10[.]10 " <<<"$auth_log" || true)"
  runner_log_count="$(grep -Ec "Accepted publickey for ${EXPECTED_USER} from 10[.]250[.]10[.]20 " <<<"$auth_log" || true)"
  if [[ "$ansible_log_count" -lt 1 || "$runner_log_count" -lt 1 ]]; then
    echo "ERROR: sshd public-key acceptance evidence is incomplete" >&2
    exit 17
  fi

  backup_file="$(backup_authorized_keys before-transfer-revoke)"
  tmp_auth="$(mktemp "${HOME}/.ssh/authorized_keys.revoke.XXXXXX")"
  awk '!/p1-lb-01-stage-a-ansible-20260903/ && !/p1-lb-01-stage-a-runner-20260903/' \
    "$AUTHORIZED_KEYS" > "$tmp_auth"
  install -m 0600 "$tmp_auth" "$AUTHORIZED_KEYS"
  rm -f -- "$tmp_auth"
  if command -v restorecon >/dev/null 2>&1; then
    restorecon -F "$AUTHORIZED_KEYS" >/dev/null 2>&1 || true
  fi
  if grep -Eq 'p1-lb-01-stage-a-(ansible|runner)-20260903' "$AUTHORIZED_KEYS"; then
    echo "ERROR: transfer key revocation verification failed" >&2
    exit 18
  fi

  for file in \
    16_positive_test_nodes.txt \
    17_positive_test_runner.txt \
    18_negative_test.txt \
    18b_secure_transfer_ansible_client.txt \
    18c_secure_transfer_runner_client.txt; do
    source_sha="$(sha256sum "$INBOX_DIR/$file" | awk '{print $1}')"
    destination_sha="$(sudo sha256sum "$EVIDENCE_DIR/$file" | awk '{print $1}')"
    if [[ "$source_sha" != "$destination_sha" ]]; then
      echo "ERROR: refusing inbox cleanup; installed Evidence hash mismatch: $file" >&2
      exit 19
    fi
  done

  rm -f -- \
    "$INBOX_DIR/16_positive_test_nodes.txt" \
    "$INBOX_DIR/17_positive_test_runner.txt" \
    "$INBOX_DIR/18_negative_test.txt" \
    "$INBOX_DIR/18b_secure_transfer_ansible_client.txt" \
    "$INBOX_DIR/18c_secure_transfer_runner_client.txt"

  transfer_evidence="$STATE_DIR/18a_secure_evidence_transfer_control.txt"
  {
    echo "test=P1-LB-01 Stage A secure Evidence transfer control"
    echo "timestamp=$(date --iso-8601=seconds)"
    echo "lb_host=$(hostnamectl --static)"
    echo "lb_user=$(id -un)"
    echo "authentication=publickey-only"
    echo "password_authentication_used=NO"
    echo "host_key_algorithm=ED25519"
    echo "lb_host_key_fingerprint=$(host_key_fingerprint | awk '{print $2}')"
    for role in ansible runner; do
      echo "${role}_source=$(awk -F= '$1 == "allowed_source" {print $2}' "$STATE_DIR/authorize_${role}.txt")"
      echo "${role}_key_fingerprint=$(awk -F= '$1 == "key_fingerprint" {print $2}' "$STATE_DIR/authorize_${role}.txt")"
      echo "${role}_restriction=from,restrict,forced-command"
    done
    echo "ansible_publickey_accept_log_count=$ansible_log_count"
    echo "runner_publickey_accept_log_count=$runner_log_count"
    for file in \
      16_positive_test_nodes.txt \
      17_positive_test_runner.txt \
      18_negative_test.txt \
      18b_secure_transfer_ansible_client.txt \
      18c_secure_transfer_runner_client.txt; do
      echo "${file}.sha256=$(sudo sha256sum "$EVIDENCE_DIR/$file" | awk '{print $1}')"
      echo "${file}.mode=$(sudo stat -c '%a' "$EVIDENCE_DIR/$file")"
    done
    echo "authorized_keys_backup=$backup_file"
    echo "authorized_keys_backup_sha256=$(sha256sum "$backup_file" | awk '{print $1}')"
    echo "authorized_transfer_key_count_after_revoke=$(grep -Ec 'p1-lb-01-stage-a-(ansible|runner)-20260903' "$AUTHORIZED_KEYS" || true)"
    echo "protected_inbox_mode=$(stat -c '%a' "$INBOX_DIR")"
    echo "protected_inbox_file_count_after_cleanup=$(find "$INBOX_DIR" -maxdepth 1 -type f | wc -l)"
    echo "verdict=PASS"
  } > "$transfer_evidence"
  chmod 0600 "$transfer_evidence"
  sudo install -m 0640 "$transfer_evidence" "$EVIDENCE_DIR/18a_secure_evidence_transfer_control.txt"
  sudo cat "$EVIDENCE_DIR/18a_secure_evidence_transfer_control.txt"
  echo "TRANSFER_KEYS_REVOKED_AND_EVIDENCE_ISSUED"
}

mode="${1:-}"
case "$mode" in
  precheck)
    [[ $# -eq 1 ]] || { usage; exit 1; }
    precheck
    ;;
  prepare)
    [[ $# -eq 1 ]] || { usage; exit 1; }
    prepare
    ;;
  authorize)
    [[ $# -eq 2 ]] || { usage; exit 1; }
    authorize "$2"
    ;;
  merge)
    [[ $# -eq 3 ]] || { usage; exit 1; }
    merge_file "$2" "$3"
    ;;
  revoke-and-evidence)
    [[ $# -eq 1 ]] || { usage; exit 1; }
    revoke_and_evidence
    ;;
  *)
    usage
    exit 1
    ;;
esac
