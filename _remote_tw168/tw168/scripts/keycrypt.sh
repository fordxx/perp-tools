#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ssh_key_helper.sh
source "${SCRIPT_DIR}/ssh_key_helper.sh"

usage() {
  cat <<'USAGE'
Usage:
  scripts/keycrypt.sh encrypt <key.pem> [out.enc] [--force]
  scripts/keycrypt.sh decrypt <key.pem.enc> [out.pem] [--force]

Notes:
  - This uses OpenSSL AES-256-GCM with PBKDF2.
  - Prefer using .enc keys with scripts that support it (no plaintext key stored).
USAGE
}

cmd="${1:-}"
case "$cmd" in
  encrypt)
    in_path="${2:-}"
    out_path="${3:-}"
    force="0"
    if [[ "${4:-}" == "--force" || "${3:-}" == "--force" ]]; then
      force="1"
    fi
    if [[ -z "$in_path" ]]; then
      usage
      exit 2
    fi
    if [[ -z "$out_path" || "$out_path" == "--force" ]]; then
      out_path="${in_path}.enc"
    fi
    ssh_key_encrypt_file "$in_path" "$out_path" "$force"
    echo "Encrypted: $out_path"
    ;;

  decrypt)
    in_path="${2:-}"
    out_path="${3:-}"
    force="0"
    if [[ "${4:-}" == "--force" || "${3:-}" == "--force" ]]; then
      force="1"
    fi
    if [[ -z "$in_path" ]]; then
      usage
      exit 2
    fi
    if [[ -z "$out_path" || "$out_path" == "--force" ]]; then
      out_path="${in_path%.enc}"
      if [[ "$out_path" == "$in_path" ]]; then
        out_path="${in_path}.dec"
      fi
    fi
    if [[ -e "$out_path" && "$force" != "1" ]]; then
      echo "Output exists (use --force): $out_path" >&2
      exit 2
    fi

    command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; exit 127; }
    if [[ ! -f "$in_path" ]]; then
      echo "Input not found: $in_path" >&2
      exit 2
    fi

    passphrase=""
    read -rsp "Decrypt passphrase for $in_path: " passphrase
    echo
    umask 077
    printf '%s' "$passphrase" | openssl enc -d -aes-256-gcm -pbkdf2 -iter 200000 -md sha256 \
      -in "$in_path" -out "$out_path" -pass stdin
    unset passphrase
    chmod 600 "$out_path" 2>/dev/null || true
    echo "Decrypted: $out_path"
    ;;

  -h|--help|"")
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac

