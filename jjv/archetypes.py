"""Base default archetypes: the generic jurors that auto-convene by discipline.

These are the starter panel from the scaffold (ported from the Deliberation Console
prototype). Unlike the legend and domain archetypes, they are ``library=False``: the
orchestrator may convene them automatically for any subject in their discipline.

The Drafter is the Generator for generate mode. It authors and revises; it is never
scored and never votes (``role="generator"``, empty rubric, weight 0).
"""

from __future__ import annotations

READ_ONLY = ["Read", "Grep", "Glob"]

_RULES = """

HOUSE RULES (every juror):
- You are a role archetype, not an impersonation of anyone.
- Cite the subject concretely: file, section, line, or claim. A finding without a location
  is an opinion.
- Raise a blocker only on your veto dimensions; anywhere else, the Nash_Agent broker will
  record it as cheap talk. Use "major" for serious issues outside your veto.
"""


def _anchors(name: str) -> dict:
    """Generic 1/3/5 anchors. Tune per dimension in the Archetype Studio."""
    return {
        1: f"Fails on {name.lower()}: a reviewer would block or rewrite.",
        3: f"Adequate on {name.lower()}, with gaps a strong reviewer would name.",
        5: f"Exemplary on {name.lower()}: nothing material to add.",
    }


def rubric(*dims):
    """dims: (name, weight) pairs, ordered by importance."""
    return [{"name": n, "weight": w, "anchors": _anchors(n)} for n, w in dims]


def base(id, name, discipline, persona, dims, *, weight, model, veto_dimensions=(),
         role="judge"):
    return {
        "id": id,
        "name": name,
        "discipline": discipline,
        "persona": persona.strip() + _RULES,
        "rubric": rubric(*dims),
        "weight": weight,
        "veto": bool(veto_dimensions),
        "veto_dimensions": list(veto_dimensions),
        "tools": list(READ_ONLY),
        "model": model,
        "effort": "high" if model == "opus" else "medium",
        "library": False,
        "role": role,
        "enabled": True,
        "version": 1,
    }


STAFF_ENGINEER = base(
    "staff_engineer", "Staff Engineer", "code",
    "Staff engineer in the mold of the best distributed-systems reviewers. Cares about "
    "correctness, failure modes, backpressure, and the true cost of an abstraction more "
    "than cosmetic style.",
    [("Correctness", 2.0), ("Failure modes", 1.5), ("Readability", 1.0), ("Testability", 1.0)],
    weight=1.3, model="opus",
)

SECURITY_REVIEWER = base(
    "security_reviewer", "Security Reviewer", "security",
    "Application-security specialist. Hunts injection, broken authz, secret leakage, "
    "unsafe deserialization, supply-chain risk. Rates a blocking vulnerability as blocking "
    "regardless of how nice the rest is.",
    [("Injection & input", 1.5), ("AuthZ & secrets", 1.5), ("Supply chain", 1.0)],
    weight=1.2, model="opus", veto_dimensions=["security"],
)

TECHNICAL_WRITER = base(
    "technical_writer", "Technical Writer", "docs",
    "Stripe-grade technical writer. Judges docs on whether a competent reader succeeds on "
    "the first try. Accuracy first, then completeness, then clarity and structure.",
    [("Accuracy", 2.0), ("Completeness", 1.2), ("Clarity", 1.0), ("Structure", 0.8)],
    weight=1.0, model="sonnet",
)

PRINCIPAL_DESIGNER = base(
    "principal_designer", "Principal Designer", "design",
    "Principal product designer with an exacting eye. Judges hierarchy, consistency, "
    "accessibility, and craft. Names the element that breaks the grid and the contrast "
    "that fails WCAG.",
    [("Hierarchy", 1.2), ("Consistency", 1.0), ("Accessibility", 1.3), ("Craft", 0.8)],
    weight=1.0, model="sonnet",
)

PRODUCT_LEAD = base(
    "product_lead", "Product Lead", "product",
    "Seasoned product lead. Judges whether the work serves a real user need, whether scope "
    "is right, and whether trade-offs were made consciously. Keeps the panel honest about "
    "value, not just execution.",
    [("User value", 1.5), ("Scope", 1.0), ("Trade-offs", 1.0)],
    weight=0.9, model="sonnet",
)

DRAFTER = base(
    "drafter", "Drafter", "any",
    "Versatile principal-level author of code, docs, or design specs. Writes the strongest "
    "first draft from a brief, then revises precisely against the panel's ranked findings.",
    [],
    weight=0.0, model="opus", role="generator",
)

DEFAULT_ARCHETYPES = [
    STAFF_ENGINEER, SECURITY_REVIEWER, TECHNICAL_WRITER, PRINCIPAL_DESIGNER, PRODUCT_LEAD,
    DRAFTER,
]
