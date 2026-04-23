from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecognitionStatus:
    enabled: bool
    provider: str
    details: str
    next_step: str


class ScreenRecognitionAdapter:
    """Scaffold for future on-screen card and number detection."""

    def status(self) -> RecognitionStatus:
        return RecognitionStatus(
            enabled=False,
            provider="placeholder",
            details=(
                "Screen recognition is scaffolded but not connected to a live OCR or "
                "table-capture provider yet."
            ),
            next_step=(
                "Attach a screenshot source, card detector, and OCR pass for pot, stacks, "
                "and bet sizing."
            ),
        )
