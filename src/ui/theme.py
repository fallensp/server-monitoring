"""Shared dashboard theme.

Single source of truth for the dark-theme CSS used by the main overview
page (app_v2.py) and every page under pages/.
"""

BASE_CSS = """
    /* Import fonts */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');

    /* Root variables */
    :root {
        --bg-primary: #0a0a0f;
        --bg-secondary: #12121a;
        --bg-card: #1a1a24;
        --bg-card-hover: #22222e;
        --accent-orange: #ff6b2c;
        --accent-orange-dim: rgba(255, 107, 44, 0.15);
        --accent-green: #00d97e;
        --accent-green-dim: rgba(0, 217, 126, 0.15);
        --accent-red: #ff4757;
        --accent-red-dim: rgba(255, 71, 87, 0.15);
        --accent-blue: #4da3ff;
        --accent-blue-dim: rgba(77, 163, 255, 0.15);
        --accent-purple: #a855f7;
        --text-primary: #ffffff;
        --text-secondary: #8b8b9e;
        --text-muted: #5c5c6e;
        --border-color: #2a2a3a;
    }

    /* Global styles */
    .stApp {
        background: var(--bg-primary);
        font-family: 'Outfit', sans-serif;
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: var(--bg-secondary);
        border-right: 1px solid var(--border-color);
    }

    [data-testid="stSidebar"] .stMarkdown {
        color: var(--text-secondary);
    }

    /* Main content area */
    .main .block-container {
        padding: 2rem 3rem;
        max-width: 100%;
    }

    /* Custom header */
    .dashboard-header {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid var(--border-color);
    }

    .dashboard-header h1 {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        font-size: 2rem;
        color: var(--text-primary);
        margin: 0;
        letter-spacing: -0.02em;
    }

    .dashboard-header .subtitle {
        color: var(--text-muted);
        font-size: 0.875rem;
        font-weight: 400;
    }

    /* Metric cards */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 16px;
        padding: 1.5rem;
        transition: all 0.2s ease;
    }

    .metric-card:hover {
        background: var(--bg-card-hover);
        border-color: var(--accent-orange);
        transform: translateY(-2px);
    }

    .metric-card .label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.5rem;
    }

    .metric-card .value {
        font-family: 'Outfit', sans-serif;
        font-size: 2.25rem;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
        margin-bottom: 0.25rem;
    }

    .metric-card .delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .metric-card .delta.positive { color: var(--accent-green); }
    .metric-card .delta.negative { color: var(--accent-red); }
    .metric-card .delta.neutral { color: var(--text-muted); }

    /* Icon badges */
    .icon-badge {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        margin-bottom: 1rem;
    }

    .icon-badge.orange { background: var(--accent-orange-dim); }
    .icon-badge.green { background: var(--accent-green-dim); }
    .icon-badge.red { background: var(--accent-red-dim); }
    .icon-badge.blue { background: var(--accent-blue-dim); }

    /* Section headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 2rem 0 1rem 0;
    }

    .section-header h2 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1.25rem;
        color: var(--text-primary);
        margin: 0;
    }

    .section-header .count {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-muted);
        background: var(--bg-card);
        padding: 4px 10px;
        border-radius: 20px;
        border: 1px solid var(--border-color);
    }

    /* Data tables */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    [data-testid="stDataFrame"] > div {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }

    /* Status badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .status-badge.running {
        background: var(--accent-green-dim);
        color: var(--accent-green);
    }

    .status-badge.stopped {
        background: var(--accent-red-dim);
        color: var(--accent-red);
    }

    .status-badge.available {
        background: var(--accent-green-dim);
        color: var(--accent-green);
    }

    /* Billing card */
    .billing-card {
        background: linear-gradient(135deg, #1a1a24 0%, #12121a 100%);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        padding: 2rem;
        position: relative;
        overflow: hidden;
    }

    .billing-card::before {
        content: '';
        position: absolute;
        top: 0;
        right: 0;
        width: 200px;
        height: 200px;
        background: radial-gradient(circle, var(--accent-orange-dim) 0%, transparent 70%);
        pointer-events: none;
    }

    .billing-card .amount {
        font-family: 'Outfit', sans-serif;
        font-size: 3rem;
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
    }

    .billing-card .currency {
        font-size: 1.5rem;
        color: var(--accent-orange);
        margin-right: 4px;
    }

    /* Streamlit overrides */
    .stSelectbox > div > div {
        background: var(--bg-card);
        border-color: var(--border-color);
    }

    .stMultiSelect > div > div {
        background: var(--bg-card);
        border-color: var(--border-color);
    }

    .stButton > button {
        background: var(--accent-orange);
        color: white;
        border: none;
        border-radius: 8px;
        font-family: 'Outfit', sans-serif;
        font-weight: 500;
        padding: 0.5rem 1.5rem;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background: #ff8551;
        transform: translateY(-1px);
    }

    .stSpinner > div {
        border-color: var(--accent-orange);
    }

    /* Radio buttons */
    .stRadio > div {
        gap: 0.5rem;
    }

    .stRadio label {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 0.5rem 1rem;
        transition: all 0.2s ease;
    }

    .stRadio label:hover {
        border-color: var(--accent-orange);
    }

    /* Warning/Info boxes */
    .stAlert {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }

    /* Divider */
    hr {
        border-color: var(--border-color);
        margin: 2rem 0;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
    }

    ::-webkit-scrollbar-thumb {
        background: var(--border-color);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }

    /* Health Summary Cards */
    .health-summary-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        transition: all 0.2s ease;
    }

    .health-summary-card:hover {
        transform: translateY(-2px);
    }

    .health-summary-card.healthy {
        border-color: rgba(0, 217, 126, 0.3);
    }

    .health-summary-card.warning {
        border-color: rgba(255, 179, 71, 0.3);
    }

    .health-summary-card.critical {
        border-color: rgba(255, 71, 87, 0.3);
    }

    .health-summary-card.total {
        border-color: rgba(77, 163, 255, 0.3);
    }

    .health-summary-icon {
        font-size: 1.25rem;
        margin-bottom: 0.25rem;
    }

    .health-summary-card.healthy .health-summary-icon { color: #00d97e; }
    .health-summary-card.warning .health-summary-icon { color: #ffb347; }
    .health-summary-card.critical .health-summary-icon { color: #ff4757; }
    .health-summary-card.total .health-summary-icon { color: #4da3ff; }

    .health-summary-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.25rem;
    }

    .health-summary-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.75rem;
        font-weight: 700;
        color: var(--text-primary);
    }

    /* Health Cards */
    .health-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.5rem;
        transition: all 0.2s ease;
    }

    .health-card:hover {
        background: var(--bg-card-hover);
    }

    .health-card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.75rem;
    }

    .health-card-title {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .health-card-icon {
        width: 24px;
        height: 24px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
    }

    .health-card-name {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1rem;
        color: var(--text-primary);
    }

    .health-card-meta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: var(--text-muted);
    }

    .health-status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        margin-bottom: 0.75rem;
    }

    .health-alerts {
        margin-bottom: 1rem;
    }

    .health-alert-item {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        background: rgba(255, 71, 87, 0.08);
        border-radius: 6px;
        margin-bottom: 4px;
    }

    .health-alert-icon {
        font-size: 0.8rem;
    }

    .health-alert-text {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: var(--text-secondary);
    }

    .health-metrics-row {
        display: flex;
        gap: 1.5rem;
    }

    .health-metric {
        flex: 1;
    }

    .health-metric-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.25rem;
    }

    .health-metric-value {
        font-family: 'Outfit', sans-serif;
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
    }
"""


def get_base_css() -> str:
    """Return the base CSS (without <style> tags)."""
    return BASE_CSS
