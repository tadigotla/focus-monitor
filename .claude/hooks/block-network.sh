#!/usr/bin/env bash
# PreToolUse hook: block outbound-network Bash commands.
#
# Reads the Claude Code hook JSON payload on stdin, extracts the candidate
# Bash command, and exits non-zero if the command looks like it reaches a
# non-localhost host. This is a safety net, not a security boundary.
#
# Allow-listed: localhost, 127.0.0.1, ollama CLI invocations.

set -euo pipefail

payload="$(cat)"

# Only care about Bash tool calls. Other tools pass through.
tool_name="$(printf '%s' "$payload" | /usr/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_name",""))' 2>/dev/null || true)"
if [[ "$tool_name" != "Bash" ]]; then
  exit 0
fi

command="$(printf '%s' "$payload" | /usr/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("command",""))' 2>/dev/null || true)"

if [[ -z "$command" ]]; then
  exit 0
fi

block() {
  local reason="$1"
  cat >&2 <<EOF
[focus-monitor privacy hook] Blocked Bash command: $reason

This repository forbids network calls to any host other than localhost /
127.0.0.1. See CLAUDE.md ("Network policy") for the rationale.

If this call is genuinely legitimate (e.g., reading upstream docs during
exploration), say so in chat and ask the user to approve the tool call
explicitly. Do not bypass the hook silently.
EOF
  exit 2
}

lower="$(printf '%s' "$command" | /usr/bin/tr '[:upper:]' '[:lower:]')"

# Short-circuit allow: purely local targets.
if printf '%s' "$lower" | /usr/bin/grep -Eq 'localhost|127\.0\.0\.1|::1'; then
  # Still fall through to check for *additional* external targets mixed in.
  :
fi

# Deny: pip install / pip download without explicit local index.
if printf '%s' "$lower" | /usr/bin/grep -Eq '(^|[^[:alnum:]_])pip[0-9]?[[:space:]]+(install|download)([[:space:]]|$)'; then
  if ! printf '%s' "$lower" | /usr/bin/grep -Eq '\--index-url[[:space:]=]+(http://)?(localhost|127\.0\.0\.1|file://)'; then
    block "pip install/download from a non-local index"
  fi
fi

# Deny: curl / wget / http / https to non-local hosts.
if printf '%s' "$lower" | /usr/bin/grep -Eq '(^|[^[:alnum:]_])(curl|wget|http|https|aria2c|httpie)[[:space:]]'; then
  # Strip anything that clearly targets localhost and see if any external URL remains.
  if printf '%s' "$lower" | /usr/bin/grep -Eoq 'https?://[^[:space:]"'"'"']+' ; then
    external="$(printf '%s' "$lower" | /usr/bin/grep -Eo 'https?://[^[:space:]"'"'"']+' | /usr/bin/grep -Ev '^(https?://)(localhost|127\.0\.0\.1|\[::1\])' || true)"
    if [[ -n "$external" ]]; then
      block "outbound HTTP(S) to: $external"
    fi
  fi
fi

# Deny: inline Python that imports network libraries or calls .get/.post against a URL.
if printf '%s' "$lower" | /usr/bin/grep -Eq 'python3?[[:space:]]+-c'; then
  if printf '%s' "$lower" | /usr/bin/grep -Eq '(requests|httpx|urllib3|aiohttp|urllib\.request)\.(get|post|put|delete|request|urlopen)'; then
    # Allow if every URL referenced is localhost.
    urls="$(printf '%s' "$lower" | /usr/bin/grep -Eo 'https?://[^[:space:]"'"'"'\)]+' || true)"
    if [[ -z "$urls" ]]; then
      block "inline Python uses a network library with no explicit URL"
    fi
    while IFS= read -r u; do
      if ! printf '%s' "$u" | /usr/bin/grep -Eq '^https?://(localhost|127\.0\.0\.1|\[::1\])'; then
        block "inline Python reaches: $u"
      fi
    done <<< "$urls"
  fi
fi

# Deny: git clone / fetch / pull from non-local remotes.
if printf '%s' "$lower" | /usr/bin/grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+(clone|fetch|pull|push|ls-remote)[[:space:]]'; then
  if printf '%s' "$lower" | /usr/bin/grep -Eoq '(https?|git|ssh)://[^[:space:]]+|[[:alnum:]][[:alnum:]._-]*@[^:]+:'; then
    remote="$(printf '%s' "$lower" | /usr/bin/grep -Eo '(https?|git|ssh)://[^[:space:]]+|[[:alnum:]][[:alnum:]._-]*@[^:]+:' | /usr/bin/grep -Ev 'localhost|127\.0\.0\.1' || true)"
    if [[ -n "$remote" ]]; then
      block "git network operation against: $remote"
    fi
  fi
fi

# ollama CLI is explicitly allowed (it talks to a local daemon).
# Everything else passes through.
exit 0
