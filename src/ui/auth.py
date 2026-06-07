"""Login gate for the dashboard.

Credentials live in .streamlit/secrets.toml (gitignored):

    [auth]
    username = "..."
    password_sha256 = "<sha256 hex of the password>"

Only the SHA-256 hash is stored; comparison uses hmac.compare_digest to
avoid timing side-channels. Failed attempts are throttled per session.
"""

import hashlib
import hmac
import time

import streamlit as st
import streamlit.components.v1 as components

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5-minute lockout after too many failures

COOKIE_NAME = "aws_monitor_session"
SESSION_DAYS = 7  # signed-cookie lifetime — login survives refreshes this long


def _credentials_configured() -> bool:
    try:
        auth = st.secrets["auth"]
        return bool(auth.get("username")) and bool(auth.get("password_sha256"))
    except (KeyError, FileNotFoundError):
        return False


def _verify(username: str, password: str) -> bool:
    auth = st.secrets["auth"]
    user_ok = hmac.compare_digest(username.strip(), auth["username"])
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    pass_ok = hmac.compare_digest(digest, auth["password_sha256"])
    return user_ok and pass_ok


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
    """Set the session cookie from a zero-height component iframe."""
    components.html(
        f"""<script>
        try {{
            window.parent.document.cookie =
                "{COOKIE_NAME}={token}; path=/; max-age={SESSION_DAYS * 86400}; SameSite=Lax";
        }} catch (e) {{
            document.cookie =
                "{COOKIE_NAME}={token}; path=/; max-age={SESSION_DAYS * 86400}; SameSite=Lax";
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


def require_login() -> None:
    """Render the login form and st.stop() until authenticated.

    Call this once at the top of the app, before any data is fetched
    or rendered. Fails closed if secrets are missing.
    """
    secret = _cookie_secret()

    if st.session_state.get("authenticated"):
        # Persist the login in a signed cookie once per session, so a page
        # refresh (which discards session_state) doesn't force a re-login
        if secret and not st.session_state.get("session_cookie_set"):
            _set_cookie_js(_make_token(st.session_state.get("auth_user", ""), secret))
            st.session_state["session_cookie_set"] = True
        return

    # Logout just happened: remove the browser cookie and block cookie
    # auto-login for the rest of this session (st.context.cookies is a
    # snapshot from page load and would still contain the old token)
    if st.session_state.pop("logging_out", False):
        _delete_cookie_js()
        st.session_state["cookie_login_blocked"] = True

    # Auto-login from a valid session cookie (set on a previous login)
    if secret and not st.session_state.get("cookie_login_blocked"):
        token = st.context.cookies.get(COOKIE_NAME)
        if token:
            user = _validate_token(token, secret)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = user
                st.session_state["session_cookie_set"] = True
                return

    if not _credentials_configured():
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
            if _verify(username, password):
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = username.strip()
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


def render_logout() -> None:
    """Sidebar logout button (renders only when authenticated)."""
    if not st.session_state.get("authenticated"):
        return
    user = st.session_state.get("auth_user", "")
    if st.button(f"🚪 Log out ({user})", width="stretch"):
        for key in ("authenticated", "auth_user", "ops_armed_at", "session_cookie_set"):
            st.session_state.pop(key, None)
        # Disarm ops on logout, and have require_login clear the cookie
        st.session_state["ops_armed"] = False
        st.session_state["logging_out"] = True
        st.rerun()
