#!/usr/bin/env bash
__SSH_KEY_HELPER_TMPFILES=()
__SSH_KEY_HELPER_TRAP_SET=""

__ssh_key_helper_cleanup() {
  local f
  for f in "${__SSH_KEY_HELPER_TMPFILES[@]:-}"; do
    rm -f "$f" || true
  done
}

__ssh_key_helper_setup_trap() {
  if [[ -n "${__SSH_KEY_HELPER_TRAP_SET}" ]]; then
    return 0
  fi
  __SSH_KEY_HELPER_TRAP_SET="1"
  trap __ssh_key_helper_cleanup EXIT INT TERM
}

ssh_key_encrypt_file() {
  local in_path="${1:-}"
  local out_path="${2:-}"
  local force="${3:-}"

  if [[ -z "$in_path" || -z "$out_path" ]]; then
    echo "ssh_key_encrypt_file: missing args" >&2
    return 2
  fi
  if [[ ! -f "$in_path" ]]; then
    echo "ssh_key_encrypt_file: input not found: $in_path" >&2
    return 2
  fi
  if [[ -e "$out_path" && "$force" != "1" ]]; then
    echo "ssh_key_encrypt_file: output exists (use --force): $out_path" >&2
    return 2
  fi
  command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; return 127; }

  local passphrase
  read -rsp "Encrypt passphrase (will not echo): " passphrase
  echo
  local passphrase2
  read -rsp "Confirm passphrase: " passphrase2
  echo
  if [[ "$passphrase" != "$passphrase2" ]]; then
    echo "Passphrases do not match." >&2
    return 2
  fi

  umask 077
  printf '%s' "$passphrase" | openssl enc -aes-256-gcm -salt -pbkdf2 -iter 200000 -md sha256 \
    -in "$in_path" -out "$out_path" -pass stdin

  unset passphrase passphrase2
  chmod 600 "$out_path" 2>/dev/null || true
}

ssh_key_decrypt_to_temp_if_needed() {
  local key_path="${1:-}"
  if [[ -z "$key_path" ]]; then
    echo "ssh_key_decrypt_to_temp_if_needed: missing key path" >&2
    return 2
  fi

  if [[ "$key_path" != *.enc ]]; then
    echo "$key_path"
    return 0
  fi

  if [[ ! -f "$key_path" ]]; then
    echo "Key not found: $key_path" >&2
    return 2
  fi

  command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; return 127; }

  __ssh_key_helper_setup_trap

  local tmp
  tmp="$(mktemp)"
  chmod 600 "$tmp" 2>/dev/null || true
  __SSH_KEY_HELPER_TMPFILES+=("$tmp")

  local passphrase
  read -rsp "Decrypt passphrase for $key_path: " passphrase
  echo

  umask 077
  printf '%s' "$passphrase" | openssl enc -d -aes-256-gcm -pbkdf2 -iter 200000 -md sha256 \
    -in "$key_path" -out "$tmp" -pass stdin

  unset passphrase
  echo "$tmp"
}
