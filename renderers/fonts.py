"""Register a Unicode-capable TTF so the ₹ (U+20B9) glyph renders.

Core PDF fonts (Helvetica) lack the Rupee sign, so it would extract as a box
character and break the amount regex. We look for a system TTF that carries the
glyph (DejaVuSans on most Linux, Arial Unicode on macOS). If none is found we
fall back to Helvetica and drop the symbol — keeping output parser-valid rather
than emitting a glyph the parser can't read.

Resolution is cached so the font is registered at most once per process.
"""

from __future__ import annotations

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_RUPEE_CP = 0x20B9

# (regular, bold) candidate pairs, in preference order.
_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf",
     "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]

_resolved: tuple[str, str, bool] | None = None


def _has_rupee(path: str) -> bool:
    try:
        return _RUPEE_CP in TTFont("probe", path).face.charToGlyph
    except Exception:
        return False


def register() -> tuple[str, str, bool]:
    """Return ``(regular_font, bold_font, rupee_supported)``."""
    global _resolved
    if _resolved is not None:
        return _resolved

    for regular, bold in _CANDIDATES:
        if _has_rupee(regular):
            try:
                pdfmetrics.registerFont(TTFont("StmtUni", regular))
                pdfmetrics.registerFont(TTFont("StmtUni-Bold", bold))
                _resolved = ("StmtUni", "StmtUni-Bold", True)
                return _resolved
            except Exception:
                break

    _resolved = ("Helvetica", "Helvetica-Bold", False)
    return _resolved


def rupee_supported() -> bool:
    return register()[2]
