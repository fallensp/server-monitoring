"""Interactive server-control UI: action bars, confirm dialogs, ops mode.

Safety model:
- Controls render only when "Operate mode" is armed (sidebar toggle,
  auto-disarms after 30 minutes).
- Stop/Reboot require typing the resource name in a modal dialog.
- Instances listed in ops_protected.json can never be actioned from the UI.
- Every action (including failures) is appended to the audit log.
"""

import html
import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.aws import control
from src.services.audit_log import log_action, read_actions

PROTECTED_PATH = Path(__file__).resolve().parent.parent.parent / "ops_protected.json"

ARM_TIMEOUT_S = 1800  # auto-disarm Operate mode after 30 minutes

# Expected terminal state after each action, for the transition tracker
TARGET_STATES = {
    ("EC2", "start"): "running",
    ("EC2", "stop"): "stopped",
    ("EC2", "reboot"): "running",
    ("RDS", "start"): "available",
    ("RDS", "stop"): "stopped",
    ("RDS", "reboot"): "available",
}

ACTION_FUNCS = {
    ("EC2", "start"): control.start_ec2_instance,
    ("EC2", "stop"): control.stop_ec2_instance,
    ("EC2", "reboot"): control.reboot_ec2_instance,
    ("RDS", "start"): control.start_rds_instance,
    ("RDS", "stop"): control.stop_rds_instance,
    ("RDS", "reboot"): control.reboot_rds_instance,
}


@st.cache_data(ttl=60)
def get_protected() -> dict[str, str]:
    """Load the protected-resource guard list (id/name -> reason).

    Fails closed: if the file exists but cannot be parsed, every resource
    is treated as protected (key "*") until the file is fixed.
    """
    if not PROTECTED_PATH.exists():
        return {}
    try:
        return json.loads(PROTECTED_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"*": "ops_protected.json is unreadable — fix or remove it"}


def _protected_reason(protected: dict, *keys: str) -> str | None:
    """Look up a protection reason; '*' blocks everything (fail closed)."""
    if "*" in protected:
        return protected["*"]
    for key in keys:
        if key and key in protected:
            return protected[key]
    return None


# ---------------------------------------------------------------------------
# Operate mode (arm switch)
# ---------------------------------------------------------------------------

def render_mode_toggle() -> bool:
    """Render the Monitor/Operate arm switch in the sidebar.

    Returns:
        True when Operate mode is armed.
    """
    # Auto-disarm after timeout (only once an arm time has been recorded)
    armed_at = st.session_state.get("ops_armed_at")
    if st.session_state.get("ops_armed") and armed_at is not None and (
        time.time() - armed_at > ARM_TIMEOUT_S
    ):
        st.session_state["ops_armed"] = False
        st.session_state.pop("ops_armed_at", None)
        st.toast("Operate mode auto-disarmed after 30 minutes", icon="🔒")

    armed = st.toggle(
        "🎛 Operate mode",
        key="ops_armed",
        help="Arm server controls (start/stop/reboot). Auto-disarms after 30 minutes. "
        "Actions affect LIVE AWS resources.",
    )
    if armed and "ops_armed_at" not in st.session_state:
        st.session_state["ops_armed_at"] = time.time()
        st.toast("Ops controls armed — actions affect live AWS", icon="🎛")
    elif not armed:
        st.session_state.pop("ops_armed_at", None)
    return armed


def render_armed_banner() -> None:
    """Persistent warning banner shown while Operate mode is armed."""
    st.markdown(
        """
        <div style="background: rgba(255, 107, 44, 0.12); border: 1px solid #ff6b2c;
                    border-radius: 8px; padding: 0.5rem 1rem; margin-bottom: 1rem;
                    font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #ff8551;">
            🎛 OPERATE MODE — server controls are armed and act on live production AWS
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------

def _service_layer_guard(kind: str, resource_id: str, display_name: str) -> str | None:
    """Defense-in-depth checks re-run at execution time (never trust UI state)."""
    if not st.session_state.get("ops_armed"):
        return "Operate mode is not armed"
    # Re-check the arm timeout here too: a confirm dialog left open reruns in
    # isolation and would otherwise bypass the sidebar's auto-disarm check.
    armed_at = st.session_state.get("ops_armed_at")
    if armed_at is None or time.time() - armed_at > ARM_TIMEOUT_S:
        # Don't mutate the toggle's widget key here (dialog scope) — the
        # sidebar's own check disarms it on the next full rerun.
        return "Operate mode timed out — arm it again"
    reason = _protected_reason(get_protected(), resource_id, display_name)
    if reason:
        return f"Protected resource: {reason}"
    return None


def _execute_action(kind: str, action: str, resource_id: str, display_name: str, region: str) -> None:
    guard_error = _service_layer_guard(kind, resource_id, display_name)
    if guard_error:
        log_action(kind, resource_id, action, region, False, f"denied: {guard_error}")
        st.toast(f"Denied: {guard_error}", icon="🚫")
        return

    result = ACTION_FUNCS[(kind, action)](resource_id, region)
    log_action(kind, resource_id, action, region, result.success, result.message)

    if result.success and (kind, action) == ("EC2", "reboot"):
        # A soft EC2 reboot never changes the describe_instances state, so
        # there is no transition to track — log the request and move on.
        st.toast(f"Reboot requested for {display_name} (soft reboot — no state change to track)", icon="🔄")
        return

    if result.success:
        st.session_state.setdefault("pending_ops", []).append({
            "kind": kind,
            "id": resource_id,
            "name": display_name,
            "action": action,
            "region": region,
            "target": TARGET_STATES[(kind, action)],
            "started_at": time.time(),
        })
        st.toast(f"{action.title()} requested for {display_name}", icon="✅")
    else:
        st.toast(f"{action.title()} failed: {result.message}", icon="❌")


@st.dialog("Confirm action")
def _confirm_dialog(
    kind: str,
    action: str,
    resource_id: str,
    display_name: str,
    region: str,
    meta: str,
    require_typed: bool,
) -> None:
    """Modal confirmation. Stop/reboot require typing the resource name."""
    icon = {"start": "▶️", "stop": "🛑", "reboot": "🔄"}.get(action, "⚙️")
    danger = action in ("stop", "reboot")
    border = "#ff4757" if danger else "#00d97e"

    st.markdown(
        f"""
        <div style="border: 1px solid {border}; border-left: 4px solid {border};
                    border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <div style="font-size: 1.1rem; font-weight: 600;">{icon} {action.title()} — {html.escape(display_name)}</div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #8b8b9e; margin-top: 0.5rem;">
                {html.escape(resource_id)} · {html.escape(region)} · {html.escape(meta)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if kind == "RDS" and action == "stop":
        st.warning("AWS automatically restarts stopped RDS instances after **7 days**.", icon="⏰")
    if kind == "EC2" and action == "stop":
        st.caption("A non-Elastic public IP will be released on stop. EBS volumes keep billing.")

    confirmed = True
    if require_typed:
        typed = st.text_input(
            f"Type **{display_name}** to confirm",
            key=f"confirm_typed_{kind}_{resource_id}_{action}",
            placeholder=display_name,
        )
        confirmed = typed.strip() == display_name

    col1, col2 = st.columns(2)
    if col1.button(
        f"{icon} Confirm {action}",
        type="primary",
        disabled=not confirmed,
        width="stretch",
        key=f"confirm_btn_{kind}_{resource_id}_{action}",
    ):
        _execute_action(kind, action, resource_id, display_name, region)
        st.rerun()
    if col2.button("Cancel", width="stretch", key=f"cancel_btn_{kind}_{resource_id}_{action}"):
        st.rerun()


# ---------------------------------------------------------------------------
# Action bars
# ---------------------------------------------------------------------------

def _render_protected_badge(reason: str) -> None:
    st.markdown(
        f"""
        <span style="background: rgba(255, 71, 87, 0.15); color: #ff4757; padding: 4px 12px;
                     border-radius: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
                     font-weight: 600;">🔒 PROTECTED — {html.escape(reason)}</span>
        """,
        unsafe_allow_html=True,
    )


def render_ec2_action_bar(inst: dict, armed: bool) -> None:
    """Action bar for the selected EC2 instance row."""
    name = inst.get("Name") if inst.get("Name") and inst.get("Name") != "-" else inst["Instance ID"]
    instance_id = inst["Instance ID"]
    state = inst.get("StateRaw", inst.get("State", ""))
    region = inst["Region"]
    meta = f"{inst.get('Type', '')} · {state}"

    protected_reason = _protected_reason(get_protected(), instance_id, name)

    st.markdown(
        f"""
        <div style="background: var(--bg-card); border: 1px solid var(--border-color);
                    border-radius: 12px; padding: 1rem 1.25rem; margin-top: 0.5rem;">
            <span style="font-weight: 600; font-size: 1rem;">🖥️ {html.escape(name)}</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #8b8b9e; margin-left: 10px;">
                {html.escape(instance_id)} · {html.escape(inst.get('Type', ''))} · {html.escape(region)} · state: {html.escape(state)}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if protected_reason:
        _render_protected_badge(protected_reason)

    transitional = state not in ("running", "stopped")
    blocked = (not armed) or bool(protected_reason) or transitional
    help_msg = (
        "Enable Operate mode in the sidebar to use controls" if not armed
        else protected_reason if protected_reason
        else "Instance is transitioning — wait for a stable state" if transitional
        else None
    )

    c1, c2, c3, c4, _ = st.columns([1, 1, 1, 1.2, 2.6])
    if c1.button("▶ Start", key=f"ec2_start_{instance_id}", disabled=blocked or state != "stopped", help=help_msg):
        _confirm_dialog("EC2", "start", instance_id, name, region, meta, require_typed=False)
    if c2.button("🛑 Stop", key=f"ec2_stop_{instance_id}", disabled=blocked or state != "running", help=help_msg):
        _confirm_dialog("EC2", "stop", instance_id, name, region, meta, require_typed=True)
    if c3.button("🔄 Reboot", key=f"ec2_reboot_{instance_id}", disabled=blocked or state != "running", help=help_msg):
        _confirm_dialog("EC2", "reboot", instance_id, name, region, meta, require_typed=True)
    with c4.popover("🔌 Connect"):
        public_ip = inst.get("Public IP", "-")
        if public_ip and public_ip != "-":
            st.caption("SSH")
            st.code(f"ssh ec2-user@{public_ip}", language="bash")
        else:
            st.caption("No public IP — use SSM")
        st.caption("SSM Session")
        st.code(f"aws ssm start-session --target {instance_id} --region {region}", language="bash")
        st.markdown(
            f"[Open in AWS Console](https://console.aws.amazon.com/ec2/home?region={region}#InstanceDetails:instanceId={instance_id})"
        )


def render_rds_action_bar(inst: dict, armed: bool) -> None:
    """Action bar for the selected RDS instance row."""
    db_id = inst["Identifier"]
    status = inst.get("StatusRaw", inst.get("Status", ""))
    region = inst["Region"]
    engine = inst.get("Engine", "")
    meta = f"{engine} · {inst.get('Class', '')} · {status}"

    protected_reason = _protected_reason(get_protected(), db_id)

    st.markdown(
        f"""
        <div style="background: var(--bg-card); border: 1px solid var(--border-color);
                    border-radius: 12px; padding: 1rem 1.25rem; margin-top: 0.5rem;">
            <span style="font-weight: 600; font-size: 1rem;">🗄️ {html.escape(db_id)}</span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #8b8b9e; margin-left: 10px;">
                {html.escape(engine)} · {html.escape(inst.get('Class', ''))} · {html.escape(region)} · status: {html.escape(status)}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if protected_reason:
        _render_protected_badge(protected_reason)

    transitional = status not in ("available", "stopped")
    blocked = (not armed) or bool(protected_reason) or transitional
    help_msg = (
        "Enable Operate mode in the sidebar to use controls" if not armed
        else protected_reason if protected_reason
        else "Database is transitioning — wait for a stable status" if transitional
        else None
    )

    c1, c2, c3, c4, _ = st.columns([1, 1, 1, 1.2, 2.6])
    if c1.button("▶ Start", key=f"rds_start_{db_id}", disabled=blocked or status != "stopped", help=help_msg):
        _confirm_dialog("RDS", "start", db_id, db_id, region, meta, require_typed=False)
    if c2.button("🛑 Stop", key=f"rds_stop_{db_id}", disabled=blocked or status != "available", help=help_msg):
        _confirm_dialog("RDS", "stop", db_id, db_id, region, meta, require_typed=True)
    if c3.button("🔄 Reboot", key=f"rds_reboot_{db_id}", disabled=blocked or status != "available", help=help_msg):
        _confirm_dialog("RDS", "reboot", db_id, db_id, region, meta, require_typed=True)
    with c4.popover("🔌 Connect"):
        endpoint = inst.get("Endpoint", "")
        port = inst.get("Port", "")
        if endpoint:
            st.caption("Endpoint")
            st.code(f"{endpoint}:{port}" if port else endpoint, language="text")
            if "postgres" in engine:
                st.code(f"psql -h {endpoint} -p {port or 5432} -U postgres", language="bash")
            elif "sqlserver" in engine:
                st.code(f"sqlcmd -S {endpoint},{port or 1433} -U admin", language="bash")
            elif "mysql" in engine or "mariadb" in engine:
                st.code(f"mysql -h {endpoint} -P {port or 3306} -u admin -p", language="bash")
        else:
            st.caption("No endpoint (instance stopped?)")


# ---------------------------------------------------------------------------
# Live transition tracker
# ---------------------------------------------------------------------------

def render_pending_ops(invalidate_ec2, invalidate_rds) -> None:
    """Poll in-flight actions every 5s and refresh tables on completion.

    Runs as an isolated fragment so polling never re-triggers the
    expensive multi-region inventory fetch.
    """

    @st.fragment(run_every="5s")
    def _poll():
        ops = st.session_state.get("pending_ops", [])
        if not ops:
            return

        remaining = []
        completed_kinds = set()
        for op in ops:
            if op["kind"] == "EC2":
                current = control.get_ec2_state(op["id"], op["region"])
            else:
                current = control.get_rds_status(op["id"], op["region"])
            elapsed = int(time.time() - op["started_at"])

            if current == op["target"]:
                log_action(
                    op["kind"], op["id"], f"{op['action']}:completed", op["region"],
                    True, f"reached '{current}' in {elapsed}s",
                )
                st.toast(f"{op['name']} is now {current} ({elapsed}s)", icon="✅")
                completed_kinds.add(op["kind"])
            elif elapsed > 600:
                log_action(
                    op["kind"], op["id"], f"{op['action']}:timeout", op["region"],
                    False, f"still '{current}' after {elapsed}s — stopped tracking",
                )
                st.toast(f"{op['name']} still '{current}' after 10 min — check the console", icon="⚠️")
                completed_kinds.add(op["kind"])  # refresh anyway
            else:
                st.markdown(
                    f"""
                    <div style="display: inline-flex; align-items: center; gap: 8px;
                                background: rgba(255, 179, 71, 0.12); border: 1px solid rgba(255, 179, 71, 0.4);
                                border-radius: 20px; padding: 4px 14px; margin: 0 8px 8px 0;
                                font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #ffb347;">
                        ⏳ {html.escape(op['name'])}: {html.escape(op['action'])} → currently '{html.escape(current)}' ({elapsed}s)
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                remaining.append(op)

        st.session_state["pending_ops"] = remaining
        if completed_kinds:
            if "EC2" in completed_kinds:
                invalidate_ec2()
            if "RDS" in completed_kinds:
                invalidate_rds()
            st.rerun(scope="app")

    _poll()


# ---------------------------------------------------------------------------
# Audit log viewer
# ---------------------------------------------------------------------------

def render_audit_log() -> None:
    """Expander showing recent control actions from the local audit trail."""
    entries = read_actions(50)
    with st.expander(f"🧾 Control action audit log · {len(entries)} recent"):
        if not entries:
            st.caption("No control actions recorded yet. Actions taken from this dashboard are logged here.")
            return
        df = pd.DataFrame(entries)
        cols = [c for c in ["timestamp", "user", "resource_type", "resource_id", "action", "region", "success", "message"] if c in df.columns]
        st.dataframe(
            df[cols],
            width="stretch",
            hide_index=True,
            column_config={
                "timestamp": st.column_config.TextColumn("Time (UTC)"),
                "success": st.column_config.CheckboxColumn("OK"),
            },
        )
