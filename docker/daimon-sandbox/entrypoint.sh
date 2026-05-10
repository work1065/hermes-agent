#!/bin/bash
set -e

# Docker Compose secrets are mounted read-only (0444) by default.
# No need to chmod — they're already root-only in practice since
# the container's security context handles access control.
if [ -f /run/secrets/gh_token ]; then
    # Verify it's readable by root (for the credential server)
    if ! head -c1 /run/secrets/gh_token >/dev/null 2>&1; then
        echo "WARNING: Cannot read /run/secrets/gh_token" >&2
    fi
fi

# Start credential server if binary exists
if [ -x /usr/local/bin/credential-server ]; then
    /usr/local/bin/credential-server /run/secrets/gh_token /run/git-credentials.sock &
    # Wait for socket
    for i in $(seq 1 20); do
        [ -S /run/git-credentials.sock ] && break
        sleep 0.1
    done
    # Socket permissions: accessible by agent so the broker can use it.
    # The socket protocol only serves github.com tokens.
    # The git credential helper is NOT installed for agent (chmod 700),
    # and git config credential.helper is unset.
    # The broker validates commands against an allowlist before using the token.
    if [ -S /run/git-credentials.sock ]; then
        chmod 666 /run/git-credentials.sock
    fi
fi

# Drop privileges and execute the CMD as the agent user.
# The credential server keeps running as root (backgrounded above).
# docker exec commands also default to agent user via Dockerfile USER directive,
# but the container PID 1 stays as root for the credential server.
exec gosu agent "$@"
