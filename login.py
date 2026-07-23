"""One-time interactive Garmin Connect sign-in (garminconnect >= 0.3).

Prompts for email/password (and MFA code if enabled), then stores OAuth tokens at
~/.garminconnect (or $GARMINTOKENS). Tokens auto-refresh; the MCP server only reads
the token store, so your password is never saved anywhere.

Run:  uv run python login.py
"""

import getpass
import os
import sys

from garminconnect import Garmin

TOKEN_DIR = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))


def main() -> None:
    # If tokens already work, don't ask for credentials again.
    try:
        client = Garmin()
        client.login(TOKEN_DIR)
        print(f"Existing tokens at {TOKEN_DIR} are valid — logged in as {client.get_full_name()}.")
        return
    except Exception:
        pass

    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password (not stored): ")

    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code (from email/authenticator): ").strip(),
    )
    # Passing the tokenstore makes login() save tokens there after a successful
    # credential login (0.3.x API — there is no client.garth anymore).
    client.login(TOKEN_DIR)

    print(f"Logged in as {client.get_full_name()}. Tokens saved to {TOKEN_DIR}.")
    print("You can now use the Garmin MCP server in Claude Desktop.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        msg = str(e)
        print(f"\nLogin failed: {type(e).__name__}: {msg}", file=sys.stderr)
        if "429" in msg or "rate limit" in msg.lower():
            print(
                "Garmin is rate limiting login attempts from this IP. Wait 30-60 minutes "
                "without retrying, or switch networks (e.g. phone hotspot) and try again.",
                file=sys.stderr,
            )
        else:
            print(
                "Check email/password; if you use MFA, make sure the code is current.",
                file=sys.stderr,
            )
        sys.exit(1)
