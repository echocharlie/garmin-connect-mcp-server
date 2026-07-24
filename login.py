"""One-time interactive Garmin Connect sign-in (garminconnect >= 0.3).

Prompts for email/password (and MFA code if enabled), then stores OAuth tokens at
~/.garminconnect (or $GARMINTOKENS). Tokens auto-refresh; the MCP server only reads
the token store, so your password is never saved anywhere.

Run:            uv run python login.py
Switch account: uv run python login.py --force
"""

import getpass
import sys

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from server import TOKEN_DIR  # single source of truth for where tokens live

RATE_LIMIT_ADVICE = (
    "Garmin is rate limiting login attempts from this IP. Wait 30-60 minutes without "
    "retrying, or switch networks (e.g. phone hotspot) and try again."
)


def main(force: bool = False) -> None:
    # If tokens already work, don't ask for credentials again (unless --force).
    if not force:
        try:
            client = Garmin()
            client.login(TOKEN_DIR)
            print(f"Existing tokens at {TOKEN_DIR} are valid — logged in as {client.get_full_name()}.")
            print("To sign in as a different account, run:  python login.py --force")
            return
        except GarminConnectTooManyRequestsError:
            # Don't fall through to a credential login — that would deepen the block,
            # and the stored tokens may well still be fine.
            print(f"Could not verify existing tokens: {RATE_LIMIT_ADVICE}", file=sys.stderr)
            sys.exit(1)
        except GarminConnectAuthenticationError:
            pass  # tokens missing/invalid — proceed to credential login
        except Exception as e:
            print(
                f"Could not verify existing tokens ({type(e).__name__}: {e}).\n"
                "This looks like a network or Garmin outage, not bad tokens — check your "
                "connection and try again. Use --force to sign in with credentials anyway.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not sys.stdin.isatty():
        # getpass falls back to echoing the password when stdin isn't a terminal,
        # which would leak it into captured output (e.g. an agent transcript).
        print(
            "login.py needs an interactive terminal to prompt for your password "
            "securely. Run it yourself in Terminal/PowerShell.",
            file=sys.stderr,
        )
        sys.exit(1)

    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Garmin Connect password (not stored): ")

    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code (from email/authenticator): ").strip(),
    )
    # Passing the tokenstore makes login() save tokens there after a successful
    # credential login (0.3.x API).
    client.login(TOKEN_DIR)

    print(f"Logged in as {client.get_full_name()}. Tokens saved to {TOKEN_DIR}.")
    print("You can now use the Garmin MCP server in Claude Desktop.")


if __name__ == "__main__":
    try:
        main(force="--force" in sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit(1)
    except GarminConnectTooManyRequestsError:
        print(f"\nLogin failed: {RATE_LIMIT_ADVICE}", file=sys.stderr)
        sys.exit(1)
    except GarminConnectAuthenticationError as e:
        print(f"\nLogin failed: {e}", file=sys.stderr)
        print(
            "Check email/password; if you use MFA, make sure the code is current.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"\nLogin failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
