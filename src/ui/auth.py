"""Login gate for the dashboard, with per-page roles.

Credentials live in .streamlit/secrets.toml (gitignored):

    [auth]
    username = "..."                      # primary account (role "admin")
    password_sha256 = "<sha256 hex of the password>"
    cookie_secret = "..."

    [[auth.users]]                        # additional accounts
    username = "..."
    password_sha256 = "..."
    role = "c5"                           # defaults to "c5" (least privilege)

Roles map to the pages a user may open (see ROLE_PAGES). Only SHA-256
hashes are stored; comparison uses hmac.compare_digest to avoid timing
side-channels. Failed attempts are throttled per session.
"""

import hashlib
import hmac
import html
import time

import streamlit as st
import streamlit.components.v1 as components

from src.ui import nav

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5-minute lockout after too many failures

COOKIE_NAME = "aws_monitor_session"
SESSION_DAYS = 7  # signed-cookie lifetime — login survives refreshes this long

# Pages each role may open. Page keys match src.ui.nav.PAGES.
ROLE_PAGES = {
    "admin": frozenset({"overview", "c5"}),
    "c5": frozenset({"c5"}),
}


class SecretsUnavailable(Exception):
    """secrets.toml could not be read right now (missing or mid-save)."""


def _load_accounts() -> dict[str, dict]:
    """Return {username: account} from secrets.toml.

    Raises:
        SecretsUnavailable: the file can't be read at this moment.
        ValueError: the config is invalid — duplicate usernames (which
            would make authentication and role lookup disagree, a
            privilege-escalation hazard) or a username containing "|"
            (reserved as the cookie-token delimiter). Both fail closed.
    """
    try:
        auth = st.secrets["auth"]
    except KeyError:
        return {}  # secrets parsed fine, just no [auth] section
    except Exception as e:  # FileNotFoundError / parse error mid-save
        raise SecretsUnavailable(str(e)) from e

    raw = []
    if auth.get("username") and auth.get("password_sha256"):
        raw.append({
            "username": auth["username"],
            "password_sha256": auth["password_sha256"],
            "role": auth.get("role", "admin"),  # primary account is the admin
        })
    for user in auth.get("users", ()):
        if user.get("username") and user.get("password_sha256"):
            raw.append({
                "username": user["username"],
                "password_sha256": user["password_sha256"],
                "role": user.get("role", "c5"),  # least-privilege default
            })

    accounts: dict[str, dict] = {}
    for user in raw:
        name = user["username"]
        if "|" in name:
            raise ValueError(f'username {name!r} contains "|" (reserved)')
        if name in accounts:
            raise ValueError(f"duplicate username {name!r} in secrets.toml")
        accounts[name] = user
    return accounts


def _verify(accounts: dict[str, dict], username: str, password: str) -> dict | None:
    """Return the matching account dict, or None.

    Checks every account without early exit so response time doesn't
    leak which username exists. Usernames are unique (enforced by
    _load_accounts), so the matched account is unambiguous and its role
    is the role of the credential that actually authenticated.
    """
    candidate = username.strip()
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    matched = None
    for user in accounts.values():
        user_ok = hmac.compare_digest(candidate, user["username"])
        pass_ok = hmac.compare_digest(digest, user["password_sha256"])
        if user_ok and pass_ok:
            matched = user
    return matched


def allowed_pages() -> frozenset[str]:
    """Page keys the signed-in user may open (empty set pre-login)."""
    role = st.session_state.get("auth_role", "")
    return ROLE_PAGES.get(role, frozenset())


# ---------------------------------------------------------------------------
# Session cookie (survives page refreshes — session_state does not)
# ---------------------------------------------------------------------------

def _cookie_secret() -> str | None:
    try:
        return st.secrets["auth"].get("cookie_secret") or None
    except (KeyError, FileNotFoundError):
        return None


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _make_token(username: str, secret: str) -> str:
    expiry = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{username}|{expiry}"
    return f"{payload}|{_sign(payload, secret)}"


def _validate_token(token: str, secret: str) -> str | None:
    """Return the username if the cookie token is authentic and unexpired."""
    parts = token.split("|")
    if len(parts) != 3:
        return None
    username, expiry, sig = parts
    if not hmac.compare_digest(sig, _sign(f"{username}|{expiry}", secret)):
        return None
    try:
        if time.time() > int(expiry):
            return None
    except ValueError:
        return None
    return username


def _set_cookie_js(token: str) -> None:
    """Set the session cookie from a zero-height component iframe.

    Adds the Secure attribute when the page is served over HTTPS; the
    current deployment is plain HTTP behind nginx, so it can't be set
    unconditionally without breaking cookie persistence there.
    """
    components.html(
        f"""<script>
        var secure = "";
        try {{
            if (window.parent.location.protocol === "https:") secure = "; Secure";
        }} catch (e) {{
            if (window.location.protocol === "https:") secure = "; Secure";
        }}
        var cookie =
            "{COOKIE_NAME}={token}; path=/; max-age={SESSION_DAYS * 86400}; SameSite=Lax" + secure;
        try {{
            window.parent.document.cookie = cookie;
        }} catch (e) {{
            document.cookie = cookie;
        }}
        </script>""",
        height=0,
    )


def _delete_cookie_js() -> None:
    components.html(
        f"""<script>
        try {{
            window.parent.document.cookie = "{COOKIE_NAME}=; path=/; max-age=0";
        }} catch (e) {{
            document.cookie = "{COOKIE_NAME}=; path=/; max-age=0";
        }}
        </script>""",
        height=0,
    )


def require_login(page: str = "overview") -> None:
    """Render the login form and st.stop() until authenticated AND the
    signed-in account's role may open this page.

    Call this once at the top of each page, before any data is fetched
    or rendered. Fails closed if secrets are missing.

    Args:
        page: page key from src.ui.nav.PAGES ("overview", "c5")
    """
    secret = _cookie_secret()

    # Load the account table once per run. Invalid config always fails
    # closed; a transient read failure must NOT destroy live sessions.
    accounts: dict[str, dict] | None
    try:
        accounts = _load_accounts()
        config_error = None
    except SecretsUnavailable:
        accounts, config_error = None, "unavailable"
    except ValueError as e:
        accounts, config_error = None, f"invalid: {e}"

    if st.session_state.get("authenticated"):
        if accounts is None:
            # secrets.toml is unreadable or invalid this run (e.g. being
            # edited on the host). Refuse to render, but keep the session
            # and cookie — logging everyone out over a mid-save blip is
            # the regression we're avoiding; fixing secrets restores it.
            if config_error == "unavailable":
                st.error("🔒 Login configuration is temporarily unreadable — reload shortly.")
            else:
                st.error(f"🔒 Login configuration {config_error}. Refusing to serve until fixed.")
            st.stop()
        # Re-resolve the account from secrets every run so edits
        # (role change, account removal) apply immediately
        account = accounts.get(st.session_state.get("auth_user", ""))
        if account is None:
            # Account no longer exists — invalidate the session
            for key in ("authenticated", "auth_user", "auth_role", "session_cookie_set"):
                st.session_state.pop(key, None)
            st.session_state["ops_armed"] = False
            st.session_state["logging_out"] = True
            st.rerun()
        role = account["role"]
        st.session_state["auth_role"] = role
        # Persist the login in a signed cookie once per session, so a page
        # refresh (which discards session_state) doesn't force a re-login
        if secret and not st.session_state.get("session_cookie_set"):
            _set_cookie_js(_make_token(st.session_state.get("auth_user", ""), secret))
            st.session_state["session_cookie_set"] = True
        _require_page_access(page, role)
        return

    # Logout just happened: remove the browser cookie and block cookie
    # auto-login for the rest of this session (st.context.cookies is a
    # snapshot from page load and would still contain the old token)
    if st.session_state.pop("logging_out", False):
        _delete_cookie_js()
        st.session_state["cookie_login_blocked"] = True

    # Auto-login from a valid session cookie (set on a previous login)
    if secret and accounts and not st.session_state.get("cookie_login_blocked"):
        token = st.context.cookies.get(COOKIE_NAME)
        if token:
            user = _validate_token(token, secret)
            account = accounts.get(user) if user else None
            if account:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = account["username"]
                st.session_state["auth_role"] = account["role"]
                st.session_state["session_cookie_set"] = True
                _require_page_access(page, account["role"])
                return

    if config_error is not None and config_error != "unavailable":
        st.error(f"🔒 Login configuration {config_error}. Refusing to start until fixed.")
        st.stop()

    if not accounts:
        st.error(
            "🔒 Login is not configured. Create `.streamlit/secrets.toml` with an "
            "`[auth]` section (username + password_sha256). Refusing to start without it."
        )
        st.stop()

    # Lockout after repeated failures
    locked_until = st.session_state.get("auth_locked_until", 0)
    if time.time() < locked_until:
        remaining = int(locked_until - time.time())
        st.error(f"🔒 Too many failed attempts. Try again in {remaining}s.")
        st.stop()

    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown(
            """
            <div style="text-align: center; padding: 3rem 0 1rem 0;">
                <div style="font-size: 2.5rem;">⚡</div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.5rem; color: #fff;">AWS Monitor</div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em;">Sign in to continue</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

        if submitted:
            account = _verify(accounts, username, password)
            if account:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = account["username"]
                st.session_state["auth_role"] = account["role"]
                st.session_state.pop("auth_failures", None)
                st.session_state.pop("auth_locked_until", None)
                st.session_state.pop("cookie_login_blocked", None)
                st.session_state["session_cookie_set"] = False  # set on next run
                st.rerun()
            else:
                failures = st.session_state.get("auth_failures", 0) + 1
                st.session_state["auth_failures"] = failures
                if failures >= MAX_ATTEMPTS:
                    st.session_state["auth_locked_until"] = time.time() + LOCKOUT_SECONDS
                    st.session_state["auth_failures"] = 0
                    st.error("🔒 Too many failed attempts — locked for 5 minutes.")
                else:
                    st.error(f"Invalid username or password ({failures}/{MAX_ATTEMPTS} attempts).")

    st.stop()


def _require_page_access(page: str, role: str) -> None:
    """Block the page (with a way out) if the role may not open it.

    Streamlit pages are directly URL-addressable, so hiding a nav link is
    not enough — every page must enforce its own access.
    """
    if page in ROLE_PAGES.get(role, frozenset()):
        return

    user = st.session_state.get("auth_user", "")
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown(
            f"""
            <div style="text-align: center; padding: 3rem 0 1rem 0;">
                <div style="font-size: 2.5rem;">🔒</div>
                <div style="font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1.5rem; color: #fff;">Access restricted</div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #5c5c6e; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.5rem;">
                    {html.escape(user)} · role "{html.escape(role)}" cannot open this page</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        accessible = ROLE_PAGES.get(role, frozenset())
        if accessible:
            st.markdown("You can open:")
            nav.render_nav(accessible)
        else:
            st.warning("This account has no accessible pages — contact the administrator.")
        render_logout()
    st.stop()


def render_logout() -> None:
    """Logout button (renders only when authenticated)."""
    if not st.session_state.get("authenticated"):
        return
    user = st.session_state.get("auth_user", "")
    if st.button(f"🚪 Log out ({user})", width="stretch"):
        for key in ("authenticated", "auth_user", "auth_role", "ops_armed_at",
                    "session_cookie_set"):
            st.session_state.pop(key, None)
        # Disarm ops on logout, and have require_login clear the cookie
        st.session_state["ops_armed"] = False
        st.session_state["logging_out"] = True
        st.rerun()
