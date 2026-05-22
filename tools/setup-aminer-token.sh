#!/usr/bin/env sh
set -eu

NAME="AMINER_API_KEY"
STATUS=0
CLEAR=0
FORCE=0
PROCESS_ONLY=0
TOKEN=""

usage() {
  cat <<'EOF'
Usage: tools/setup-aminer-token.sh [--status] [--clear] [--force] [--process-only] [--token <value>]

Configures AMINER_API_KEY for macOS/Linux shells.
The token value is never printed.

Options:
  --status        Show whether AMINER_API_KEY is configured
  --clear         Remove AMINER_API_KEY from the selected shell profile
  --force         Replace an existing token without prompting
  --process-only  Show safe commands for configuring the current shell only
  --token VALUE   Use VALUE instead of prompting interactively
  -h, --help      Show this help
EOF
}

hash_prefix() {
  if [ -z "${1:-}" ]; then
    printf ''
    return 0
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print toupper(substr($1,1,12))}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | awk '{print toupper(substr($1,1,12))}'
  else
    printf 'UNAVAILABLE'
  fi
}

shell_profile() {
  if [ -n "${AMINER_TOKEN_PROFILE:-}" ]; then
    printf '%s\n' "$AMINER_TOKEN_PROFILE"
    return 0
  fi
  shell_name=$(basename "${SHELL:-sh}")
  case "$shell_name" in
    zsh) printf '%s\n' "$HOME/.zshrc" ;;
    bash)
      if [ "$(uname -s 2>/dev/null || printf unknown)" = "Darwin" ]; then
        printf '%s\n' "$HOME/.bash_profile"
      else
        printf '%s\n' "$HOME/.bashrc"
      fi
      ;;
    *) printf '%s\n' "$HOME/.profile" ;;
  esac
}

show_status() {
  value="${AMINER_API_KEY:-}"
  profile=$(shell_profile)
  configured="no"
  length=0
  prefix=""
  if [ -n "$value" ]; then
    configured="yes"
    length=${#value}
    prefix=$(hash_prefix "$value")
  fi

  printf '\nAMiner token status (token value is never printed):\n'
  printf '  Process configured: %s\n' "$configured"
  printf '  Process length: %s\n' "$length"
  printf '  Process sha256 prefix: %s\n' "$prefix"
  printf '  Shell profile: %s\n' "$profile"
  if [ -f "$profile" ] && grep -q "^export ${NAME}=" "$profile"; then
    printf '  Profile entry: yes\n'
  else
    printf '  Profile entry: no\n'
  fi
}

write_profile_token() {
  profile=$1
  token=$2
  tmp="${profile}.tmp.$$"
  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  grep -v "^export ${NAME}=" "$profile" > "$tmp" || true
  printf '\nexport %s=%s\n' "$NAME" "$(printf '%s' "$token" | sed "s/'/'\\\\''/g; s/.*/'&'/")" >> "$tmp"
  mv "$tmp" "$profile"
}

clear_profile_token() {
  profile=$1
  tmp="${profile}.tmp.$$"
  if [ ! -f "$profile" ]; then
    return 0
  fi
  grep -v "^export ${NAME}=" "$profile" > "$tmp" || true
  mv "$tmp" "$profile"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --status) STATUS=1 ;;
    --clear) CLEAR=1 ;;
    --force) FORCE=1 ;;
    --process-only) PROCESS_ONLY=1 ;;
    --token)
      shift
      if [ "$#" -eq 0 ]; then
        printf 'Missing value for --token\n' >&2
        exit 2
      fi
      TOKEN=$1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

profile=$(shell_profile)

if [ "$STATUS" -eq 1 ]; then
  show_status
  exit 0
fi

if [ "$CLEAR" -eq 1 ]; then
  if [ "$PROCESS_ONLY" -eq 1 ]; then
    printf 'Run this in your current shell to clear %s:\n' "$NAME"
    printf 'unset %s\n' "$NAME"
  else
    clear_profile_token "$profile"
    printf 'Cleared %s from %s.\n' "$NAME" "$profile"
  fi
  show_status
  exit 0
fi

if [ "$PROCESS_ONLY" -eq 1 ]; then
  printf 'A child script cannot modify the parent shell environment directly.\n'
  printf 'Run these commands in your current shell to configure %s without echoing the token:\n' "$NAME"
  printf 'read -r -s %s\n' "$NAME"
  printf 'export %s\n' "$NAME"
  exit 0
fi

if [ -f "$profile" ] && grep -q "^export ${NAME}=" "$profile" && [ "$FORCE" -ne 1 ]; then
  printf '%s already exists in %s.\n' "$NAME" "$profile"
  printf 'Use --force to replace it, --status to inspect it, or --clear to remove it.\n'
  show_status
  exit 0
fi

if [ -z "$TOKEN" ]; then
  printf 'Paste AMiner token: ' >&2
  stty -echo 2>/dev/null || true
  IFS= read -r TOKEN
  stty echo 2>/dev/null || true
  printf '\n' >&2
fi

if [ -z "$TOKEN" ]; then
  printf 'Empty token. Nothing was changed.\n' >&2
  exit 1
fi
case "$TOKEN" in
  *[![:graph:]]*)
    printf 'Token contains whitespace or control characters. Nothing was changed.\n' >&2
    exit 1
    ;;
esac

write_profile_token "$profile" "$TOKEN"
export AMINER_API_KEY="$TOKEN"

printf 'Configured %s in %s.\n' "$NAME" "$profile"
printf 'Open a new terminal, or run: . "%s"\n' "$profile"
show_status
