"""Billing center classification for resources.

Mirrors the billing-center definitions in CLAUDE.md. Cost allocation tags
are not activated in Cost Explorer, so classification happens client-side
from instance tags + regions.
"""

BILLING_CENTERS = {
    "titantech": {
        "label": "BC1 · Titantech",
        "color": "#ff6b2c",
        "regions": ["ap-southeast-1", "ap-southeast-3"],
        "project_tag": "titantech",
    },
    "tokyo": {
        "label": "BC2 · Tokyo",
        "color": "#4da3ff",
        "regions": ["ap-northeast-1"],
        "project_tag": None,  # everything in Tokyo
    },
    "bubble": {
        "label": "BC3 · Bubble",
        "color": "#a855f7",
        "regions": ["ap-southeast-1"],
        "project_tag": "bubble",
    },
    "pictureworks": {
        "label": "BC4 · Pictureworks",
        "color": "#00d97e",
        "regions": ["ap-east-1"],
        "project_tag": None,  # everything in Hong Kong
    },
}


def classify_resource(region: str, project_tag: str | None = None) -> str | None:
    """Classify a resource into a billing center key.

    Region-scoped centers (Tokyo, Hong Kong) win outright; Singapore
    resources are split by their Project tag, defaulting to titantech
    (which absorbs shared Singapore infrastructure per CLAUDE.md).

    Args:
        region: AWS region of the resource
        project_tag: Value of the resource's Project tag, if any

    Returns:
        Billing center key, or None if outside all centers
    """
    if region == "ap-northeast-1":
        return "tokyo"
    if region == "ap-east-1":
        return "pictureworks"
    if region in ("ap-southeast-1", "ap-southeast-3"):
        if project_tag and project_tag.lower() == "bubble":
            return "bubble"
        return "titantech"
    return None


def get_center_label(center_key: str | None) -> str:
    """Human-readable label for a billing center key."""
    if center_key is None:
        return "Unassigned"
    return BILLING_CENTERS.get(center_key, {}).get("label", center_key)


def get_center_color(center_key: str | None) -> str:
    """Accent color for a billing center key."""
    if center_key is None:
        return "#5c5c6e"
    return BILLING_CENTERS.get(center_key, {}).get("color", "#5c5c6e")
