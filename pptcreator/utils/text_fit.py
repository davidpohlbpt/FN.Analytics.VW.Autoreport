"""Rough text-fitting helpers (python-pptx cannot measure rendered text).

Widths are estimated from the character count with an average glyph width; this is
deliberately conservative so that text shrinks a bit early rather than wrapping.
"""

EMU_PER_PT = 12700
TEXTBOX_INSET_EMU = 2 * 91440  # default left + right inset of a PowerPoint text box
AVG_GLYPH_EM = 0.56
BOLD_FACTOR = 1.06


def line_width_pt(text: str, size_pt: float, bold: bool = False) -> float:
    return len(text) * size_pt * AVG_GLYPH_EM * (BOLD_FACTOR if bold else 1.0)


def fit_font_size(
    lines: list[str],
    width_emu: int,
    size_pt: float,
    *,
    bold: bool = False,
    min_pt: float = 9.0,
) -> float:
    """Largest size <= size_pt (in 0.5 pt steps) at which every line fits on one line."""
    available_pt = max(width_emu - TEXTBOX_INSET_EMU, 1) / EMU_PER_PT
    longest = max(lines, key=len) if lines else ""
    size = float(size_pt)
    while size > min_pt and line_width_pt(longest, size, bold) > available_pt:
        size -= 0.5
    return size


def fit_wrapped_size(
    total_chars: int,
    width_emu: int,
    size_pt: float,
    *,
    max_lines: int = 2,
    min_pt: float = 9.0,
) -> float:
    """Largest size at which ``total_chars`` of flowing text fit into ``max_lines`` lines."""
    available_pt = max(width_emu - TEXTBOX_INSET_EMU, 1) / EMU_PER_PT
    size = float(size_pt)
    # Entries never break internally, so lines are not completely filled (0.8)
    while size > min_pt and total_chars * size * 0.5 > max_lines * available_pt * 0.8:
        size -= 0.5
    return size
