"""This script exists only in the fake-mail test branch."""
import os
import sys


def check_boundary(environ):
    if (environ.get("GITHUB_BASE_REF") == "main"
            or environ.get("GITHUB_REF") == "refs/heads/main"):
        raise RuntimeError("Fake mailbox test version must never target or run on main")


if __name__ == "__main__":
    try:
        check_boundary(os.environ)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
