#!/usr/bin/env bash

set -uo pipefail

ROLE="${1:-}"
INBOX_DIR="${INBOX_DIR:-${HOME}/.p1-lb-01-evidence-inbox}"
MAX_BYTES="${MAX_BYTES:-1048576}"

case "$ROLE" in
  ansible)
    EXPECTED_SOURCE="10.250.10.10"
    ALLOWED_FILES=(
      "16_positive_test_nodes.txt"
      "18_negative_test.txt"
      "18b_secure_transfer_ansible_client.txt"
    )
    ;;
  runner)
    EXPECTED_SOURCE="10.250.10.20"
    ALLOWED_FILES=(
      "17_positive_test_runner.txt"
      "18c_secure_transfer_runner_client.txt"
    )
    ;;
  *)
    echo "DENY: invalid transfer role" >&2
    exit 20
    ;;
esac

contains() {
  local expected="$1" item
  shift
  for item in "$@"; do
    [[ "$item" == "$expected" ]] && return 0
  done
  return 1
}

source_ip="${SSH_CONNECTION%% *}"
if [[ -z "$source_ip" || "$source_ip" != "$EXPECTED_SOURCE" ]]; then
  echo "DENY: source mismatch" >&2
  exit 21
fi

read -r action filename expected_sha extra <<<"${SSH_ORIGINAL_COMMAND:-}"
if [[ "$action" != "upload" || -n "${extra:-}" ]]; then
  echo "DENY: only 'upload <approved-file> <sha256>' is allowed" >&2
  exit 22
fi

if ! contains "$filename" "${ALLOWED_FILES[@]}"; then
  echo "DENY: filename is not approved for role=$ROLE" >&2
  exit 23
fi

if [[ ! "$expected_sha" =~ ^[0-9a-f]{64}$ ]]; then
  echo "DENY: invalid SHA-256 value" >&2
  exit 24
fi

if [[ ! -d "$INBOX_DIR" || "$(stat -c '%a' "$INBOX_DIR")" != "700" ]]; then
  echo "DENY: protected inbox is missing or mode is not 700" >&2
  exit 25
fi

umask 077
tmp_file="$(mktemp "$INBOX_DIR/.incoming.${filename}.XXXXXX")" || exit 26
cleanup() {
  rm -f -- "$tmp_file"
}
trap cleanup EXIT

head -c "$((MAX_BYTES + 1))" > "$tmp_file"
received_size="$(stat -c '%s' "$tmp_file")"
if (( received_size > MAX_BYTES )); then
  echo "DENY: file exceeds ${MAX_BYTES} bytes" >&2
  exit 27
fi

actual_sha="$(sha256sum "$tmp_file" | awk '{print $1}')"
if [[ "$actual_sha" != "$expected_sha" ]]; then
  echo "DENY: SHA-256 mismatch" >&2
  exit 28
fi

chmod 0600 "$tmp_file"
mv -f -- "$tmp_file" "$INBOX_DIR/$filename"
trap - EXIT

printf 'UPLOAD_OK role=%s source=%s file=%s size=%s sha256=%s\n' \
  "$ROLE" "$source_ip" "$filename" "$received_size" "$actual_sha"
