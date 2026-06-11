"""Sidebar page navigation.

The auto-generated nav is disabled in .streamlit/config.toml (it labels
the home page "app v2"); both pages call render_nav() instead.
"""

from pathlib import Path

import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PAGES = [
    ("app_v2.py", "Resource Overview", "🏠"),
    ("pages/1_C5_Monitor.py", "C5 Monitor", "🎯"),
]


def render_nav() -> None:
    for path, label, icon in _PAGES:
        # Skip missing page files: on a partial deploy a dead st.page_link
        # raises StreamlitPageNotFoundError and bricks the whole app —
        # a missing link is the better failure mode
        if (_REPO_ROOT / path).exists():
            st.page_link(path, label=label, icon=icon)
