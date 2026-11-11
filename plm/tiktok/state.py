"""Offline guard for a future TikTok posting state machine."""

_NEXT = {
    "waiting_for_consent": frozenset({"initialized", "failed"}),
    "initialized": frozenset({"transferring", "processing", "failed", "unknown"}),
    "transferring": frozenset({"processing", "failed", "unknown"}),
    "processing": frozenset({"succeeded", "failed", "unknown"}),
    "unknown": frozenset({"processing", "succeeded", "failed"}),
    "succeeded": frozenset(), "failed": frozenset(),
}


def validate_transition(current: str, next_state: str) -> None:
    if next_state not in _NEXT.get(current, ()):
        raise ValueError("invalid TikTok state transition; never reinitialize an unknown job")
