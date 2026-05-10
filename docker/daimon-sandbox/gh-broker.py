#!/usr/bin/env python3
"""gh-broker: allowlisted GitHub operations broker for sandboxed agents.

Runs as a git credential helper but instead of returning raw credentials,
it executes specific gh commands directly and returns the output.
The agent never sees the token — only the command results.

Usage (called by the agent via a custom tool or shell alias):
    gh-broker issue list -R NousResearch/hermes-agent --limit 10
    gh-broker issue create -R NousResearch/hermes-agent --title "Bug" --body "..."
    gh-broker issue comment 123 -R NousResearch/hermes-agent --body "..."
    gh-broker pr list -R NousResearch/hermes-agent
    gh-broker pr create -R NousResearch/hermes-agent --title "Fix" --body "..." --draft
    gh-broker pr comment 123 -R NousResearch/hermes-agent --body "..."
    gh-broker search issues "query" -R NousResearch/hermes-agent

Blocked: gh auth token, gh api (raw), gh ssh-key, gh secret, anything not allowlisted.
"""
import os
import socket
import subprocess
import sys

SOCKET_PATH = "/run/git-credentials.sock"
GH_REAL = "/usr/bin/gh-real"

# Allowlisted subcommands. Each entry: (subcommand, sub-subcommand or None)
# None means any sub-subcommand is allowed for that subcommand.
ALLOWED = {
    ("issue", "list"),
    ("issue", "view"),
    ("issue", "create"),
    ("issue", "comment"),
    ("issue", "close"),
    ("issue", "edit"),
    ("issue", "search"),
    ("pr", "list"),
    ("pr", "view"),
    ("pr", "create"),
    ("pr", "comment"),
    ("pr", "diff"),
    ("pr", "checks"),
    ("search", "issues"),
    ("search", "prs"),
    ("search", "code"),
}

# Blocked flags that could leak the token
BLOCKED_FLAGS = {"--with-token", "--hostname"}


def get_token():
    """Fetch token from credential server socket."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        sock.sendall(b"protocol=https\nhost=github.com\n\n")
        sock.shutdown(socket.SHUT_WR)
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        sock.close()
        for line in response.decode().splitlines():
            if line.startswith("password="):
                return line[9:]
    except Exception:
        pass
    return None


def main():
    args = sys.argv[1:]

    if len(args) < 2:
        print("Usage: gh-broker <subcommand> <action> [args...]", file=sys.stderr)
        print("Allowed: issue list/view/create/comment, pr list/view/create/comment, search issues/prs", file=sys.stderr)
        sys.exit(1)

    subcmd = args[0]
    action = args[1]

    # Check allowlist
    if (subcmd, action) not in ALLOWED:
        print(f"Denied: '{subcmd} {action}' is not an allowed operation.", file=sys.stderr)
        print(f"Allowed operations: {', '.join(f'{s} {a}' for s, a in sorted(ALLOWED))}", file=sys.stderr)
        sys.exit(1)

    # Check for blocked flags
    for flag in BLOCKED_FLAGS:
        if flag in args:
            print(f"Denied: flag '{flag}' is not allowed.", file=sys.stderr)
            sys.exit(1)

    # Get token
    token = get_token()
    if not token:
        print("Error: Could not authenticate with GitHub.", file=sys.stderr)
        sys.exit(1)

    # Run gh-real with the token, but in a subprocess so the token
    # doesn't leak into our own process environment permanently.
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    result = subprocess.run(
        [GH_REAL] + args,
        env=env,
        capture_output=False,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
