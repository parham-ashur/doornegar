"""Classify a Source into one of the 4 narrative subgroups.

The taxonomy splits Iranian media first by geography (inside vs outside
Iran) and then by stance within each side:

    درون‌مرزی  (inside)   → اصول‌گرا (principlist)   / اصلاح‌طلب (reformist)
    برون‌مرزی (outside)  → میانه‌رو (moderate)       / رادیکال (radical)

The classification is a pure function of two columns that already exist
on Source — `production_location` and `factional_alignment` — so no
schema change is required. `state_alignment` is used only as a
tiebreaker for inside-border outlets that don't have a faction tagged.
"""

from typing import Literal

NarrativeGroup = Literal[
    "principlist",
    "reformist",
    "moderate_diaspora",
    "radical_diaspora",
]

# Stable ordering used by response serializers and the frontend legend.
NARRATIVE_GROUPS_ORDER: tuple[NarrativeGroup, ...] = (
    "principlist",
    "reformist",
    "moderate_diaspora",
    "radical_diaspora",
)

SIDE_OF_GROUP: dict[NarrativeGroup, Literal["inside", "outside"]] = {
    "principlist": "inside",
    "reformist": "inside",
    "moderate_diaspora": "outside",
    "radical_diaspora": "outside",
}

# Farsi labels used as the only source of truth for group naming in the
# API + frontend. Keeping them here avoids drift across components.
GROUP_LABELS_FA: dict[NarrativeGroup, str] = {
    "principlist": "اصول‌گرا",
    "reformist": "اصلاح‌طلب",
    "moderate_diaspora": "میانه‌رو",
    "radical_diaspora": "رادیکال",
}
SIDE_LABELS_FA: dict[Literal["inside", "outside"], str] = {
    "inside": "درون‌مرزی",
    "outside": "برون‌مرزی",
}


def narrative_group(source) -> NarrativeGroup:
    """Return the 4-subgroup classification for a Source-like object.

    Accepts either an ORM Source instance or any object exposing
    `production_location`, `factional_alignment`, and `state_alignment`.
    """
    inside = getattr(source, "production_location", None) == "inside_iran"
    faction = getattr(source, "factional_alignment", None)
    state_alignment = getattr(source, "state_alignment", None)

    if inside:
        # Inside Iran: state/hardline/principlist → principlist.
        # Everything else (reformist, moderate, left, independent, NULL)
        # falls into reformist by process of elimination. This matches the
        # intuition that non-establishment Iranian outlets operate within
        # the reformist/independent camp rather than forming a third axis.
        if faction in ("hardline", "principlist") or state_alignment == "state":
            return "principlist"
        return "reformist"

    # Outside Iran: aggressive oppositional or monarchist framing lands
    # in radical; public broadcasters + mainstream indie diaspora in
    # moderate.
    if faction in ("opposition", "monarchist", "radical"):
        return "radical_diaspora"
    return "moderate_diaspora"


def side_of(group: NarrativeGroup) -> Literal["inside", "outside"]:
    """Return which of the two sides a subgroup belongs to."""
    return SIDE_OF_GROUP[group]


def counts_to_percentages(counts: dict[NarrativeGroup, int]) -> dict[NarrativeGroup, int]:
    """Normalize raw per-group article counts to integer percentages (0–100).

    The four percentages sum to 100 unless every count is zero, in which
    case all four are 0. Rounding is done with largest-remainder so the
    sum is exact.
    """
    total = sum(counts.get(g, 0) for g in NARRATIVE_GROUPS_ORDER)
    if total == 0:
        return {g: 0 for g in NARRATIVE_GROUPS_ORDER}

    # Largest-remainder rounding — keeps the four percentages summing to 100.
    raw = {g: counts.get(g, 0) * 100 / total for g in NARRATIVE_GROUPS_ORDER}
    floored = {g: int(raw[g]) for g in NARRATIVE_GROUPS_ORDER}
    assigned = sum(floored.values())
    remainders = sorted(
        NARRATIVE_GROUPS_ORDER,
        key=lambda g: (-(raw[g] - floored[g]), NARRATIVE_GROUPS_ORDER.index(g)),
    )
    for i in range(100 - assigned):
        floored[remainders[i % len(remainders)]] += 1
    return floored
