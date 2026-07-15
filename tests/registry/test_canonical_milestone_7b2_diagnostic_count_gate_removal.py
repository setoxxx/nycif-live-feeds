"""Canonical Milestone 7-B.2 completion: the GPS staged-feed match diagnostic
must not gate readiness on the stale hard-coded 430/25 count constants.

The initial M7-B.2 work removed the 204/20 constants from the adjudication and
apply stages and bound counts to a snapshot contract, but left
EXPECTED_STAGED_MATCHES = 430 and EXPECTED_PROMOTED_CACHE_KEYS = 25 as active
`stable_identity_ready` gates in the diagnostic. On any staged feed that has
rolled to a different size (e.g. the 2026-07-07 window's 155 identities), those
gates make the diagnostic report `stable_identity_ready = False` for a
perfectly valid fresh snapshot. This test locks in their removal so no runtime
count constant remains anywhere in the diagnostic -> adjudication -> apply
chain."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CHAIN_MODULES = (
    "scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
    "scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
    "scripts/apply_gps_staged_feed_integration_update.py",
    "scripts/gps_count_contract.py",
)

HISTORICAL_CONSTANTS = (
    "EXPECTED_SAFE_UPDATE_READY_COUNT",
    "EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT",
    "EXPECTED_STAGED_MATCHES",
    "EXPECTED_PROMOTED_CACHE_KEYS",
)


def _code_only(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_no_historical_count_constant_remains_in_active_chain() -> None:
    for rel in CHAIN_MODULES:
        code = _code_only(REPO_ROOT / rel)
        for token in HISTORICAL_CONSTANTS:
            assert token not in code, f"{rel} still references {token} outside comments"


def test_diagnostic_readiness_no_longer_depends_on_fixed_counts() -> None:
    code = _code_only(REPO_ROOT / "scripts/generate_gps_staged_feed_integration_match_diagnostic.py")
    # The old gate compared selected_count to a fixed 430 target and required
    # exactly 25 promoted keys. Neither may appear as a readiness condition.
    assert "selected_count == expected_count" not in code
    assert "len(promoted) == EXPECTED_PROMOTED_CACHE_KEYS" not in code
    # Readiness is now internal-consistency based.
    assert "selected_count > 0" in code
    assert "selected_identity_count == selected_count" in code
