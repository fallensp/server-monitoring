"""Sidebar page navigation.

The auto-generated nav is disabled in .streamlit/config.toml (it labels
the home page "app v2"); both pages call render_nav() instead.
"""

from pathlib import Path

import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parents[2]

# (file path, label, icon, page key) — page keys are what auth.ROLE_PAGES
# grants per role
PAGES = [
    ("app_v2.py", "Resource Overview", "🏠", "overview"),
    ("pages/1_C5_Monitor.py", "C5 Monitor", "🎯", "c5"),
]


def render_nav(allowed: frozenset[str] | set[str] | None = None) -> None:
    """Render page links, restricted to the given page keys.

    Args:
        allowed: page keys the current user may open (auth.allowed_pages());
            None shows everything (pre-login contexts only)
    """
    for path, label, icon, key in PAGES:
        if allowed is not None and key not in allowed:
            continue
        # Skip missing page files: on a partial deploy a dead st.page_link
        # raises StreamlitPageNotFoundError and bricks the whole app —
        # a missing link is the better failure mode
        if (_REPO_ROOT / path).exists():
            st.page_link(path, label=label, icon=icon)
