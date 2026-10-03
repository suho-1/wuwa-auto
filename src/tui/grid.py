"""A fixed-width table renderer for the dashboard.

Rich's ``Table`` is excellent but general-purpose: a bordered table measures
every cell, allocates padded sub-renderables, and re-crops the finished lines,
which costs roughly 3 ms per table.  With two tables per frame that dominated
the dashboard's render cost once the ``cls`` subprocess and the per-frame
config reads were gone.

The dashboard only ever needs a plain grid with known column widths, so it
builds the box drawing itself and emits the whole frame as a single
``console.print`` -- one render pass, no per-cell measurement.

Cells may be plain text (padded using its visible length) or a :class:`Cell`,
which lets a caller supply pre-styled markup while still declaring the visible
text used for padding and truncation.
"""

from __future__ import annotations

from typing import NamedTuple, Sequence, Union

from rich.markup import escape

CellLike = Union[str, "Cell"]


class Cell(NamedTuple):
    text: str
    markup: str


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _render_cell(cell: CellLike, style: str, limit: int) -> tuple:
    """Return ``(visible_text, markup)`` clipped to ``limit`` visible chars."""
    if isinstance(cell, Cell):
        text = _clip(cell.text, limit)
        if text == cell.text:
            return text, cell.markup
        # The caller pre-styled the markup, so only hand back the plain text.
        return text, escape(text)
    text = _clip(str(cell), limit)
    return text, f"[{style}]{escape(text)}[/{style}]" if style else escape(text)


def _pad(cell: CellLike, style: str, width: int, justify: str = "left") -> str:
    """Pad one cell to ``width`` content characters plus one space of margin."""
    text, markup = _render_cell(cell, style, width)
    slack = max(0, width - len(text))
    if justify == "center":
        left, right = slack // 2, slack - slack // 2
    elif justify == "right":
        left, right = slack, 0
    else:
        left, right = 0, slack
    return f" {' ' * left}{markup}{' ' * right} "


class Grid:
    """Accumulates rows, then emits them as one pre-rendered block."""

    def __init__(self, widths: Sequence[int], border: str = "green"):
        self.widths = list(widths)
        if not self.widths or any(width < 1 for width in self.widths):
            raise ValueError('Grid widths must contain positive values')
        self.border = border
        self.lines = []

    def _edge(self, left: str, middle: str, right: str) -> str:
        return (f"[{self.border}]{left}"
                + middle.join("─" * (width + 2) for width in self.widths)
                + f"{right}[/{self.border}]")

    def rule(self) -> None:
        self.lines.append(self._edge("┌", "┬", "┐"))

    def divider(self) -> None:
        self.lines.append(self._edge("├", "┼", "┤"))

    def footer(self) -> None:
        self.lines.append(self._edge("└", "┴", "┘"))

    def row(self, cells: Sequence[CellLike], styles: Sequence[str], justifies: Sequence[str]) -> None:
        expected = len(self.widths)
        if len(cells) != expected or len(styles) != expected or len(justifies) != expected:
            raise ValueError(
                f'Grid row has {len(cells)} cells, {len(styles)} styles, and '
                f'{len(justifies)} justifications; expected {expected} of each.'
            )
        padded = [_pad(cell, style, width, justify)
                  for cell, style, width, justify
                  in zip(cells, styles, self.widths, justifies, strict=True)]
        self.lines.append(f"[{self.border}]│[/{self.border}]"
                          + f"[{self.border}]│[/{self.border}]".join(padded)
                          + f"[{self.border}]│[/{self.border}]")

    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def frame_width(self) -> int:
        return sum(width + 2 for width in self.widths) + len(self.widths) + 1

    def title_line(self, title: str, style: str) -> str:
        """Centre the title so every emitted line lines up with the frame."""
        slack = max(0, self.frame_width - len(title))
        pad = " " * (slack // 2)
        return f"{pad}[{style}]{title}[/{style}]"


def render_grid(title: str, headers: Sequence[CellLike], rows: Sequence[Sequence[CellLike]],
                widths: Sequence[int], styles: Sequence[str], justifies: Sequence[str],
                border: str = "green", title_style: str = "bold yellow") -> str:
    """Build a complete bordered grid, title included, as one string."""
    expected = len(widths)
    if len(headers) != expected or len(styles) != expected or len(justifies) != expected:
        raise ValueError(
            f'Grid headers/styles/justifications must all contain {expected} values.'
        )
    grid = Grid(widths, border)
    header = [Cell(str(text), f"[bold]{escape(_clip(str(text), width))}[/bold]")
              for text, width in zip(headers, widths, strict=True)]
    if title:
        grid.lines.append(grid.title_line(_clip(title, grid.frame_width), title_style))
    grid.rule()
    grid.row(header, ["bold"] * len(headers), justifies)
    grid.divider()
    for row in rows:
        grid.row(row, styles, justifies)
    grid.footer()
    return grid.text()


def cell(text: str, style: str = "") -> Cell:
    """Build a :class:`Cell` whose markup is generated once, up front."""
    return Cell(text, f"[{style}]{escape(text)}[/{style}]" if style else escape(text))


def visible_length(markup: str) -> int:
    """Length of a markup string once tags are removed."""
    return len(visible_length_text(markup))


def visible_length_text(markup: str) -> str:
    """A markup string with its tags stripped."""
    from rich.text import Text

    return Text.from_markup(markup).plain


# --------------------------------------------------------------- panels ---
# The dashboard is a single fixed-height box, so this module also provides the
# framed shape it needs: a double-line frame with a title, a right-aligned
# status, and light rules that divide the sections.

FRAME_TL = "╔"
FRAME_TR = "╗"
FRAME_BL = "╚"
FRAME_BR = "╝"
FRAME_V = "║"
FRAME_H = "═"
LIGHT_H = "─"
LIGHT_V = "│"


class Panel:
    """A framed region whose height is known before it is rendered.

    Every emitted line is exactly `width` characters wide -- top border, body
    and bottom border alike -- so the closing edge never drifts and the frame
    can never wrap in a terminal of the same width.
    """

    def __init__(self, width: int, border: str = "cyan"):
        self.width = max(16, width)
        self.border = border
        self.lines = []          # (is_rule, markup, plain)

    @property
    def inner_width(self) -> int:
        """Usable text width inside the frame."""
        return self.width - 4

    @property
    def height(self) -> int:
        """Total rows this panel occupies once framed."""
        return len(self.lines) + 2

    def add(self, markup: str = "", plain: str = None, style: str = "") -> None:
        """Append a line, clipping it to the inner width if it overflows.

        `plain` is the visible text. Callers that already hold it pass it in
        and skip the markup parse, which matters because this runs every frame.
        """
        if plain is None:
            plain = markup if "[" not in markup else visible_length_text(markup)
        if len(plain) > self.inner_width:
            plain = plain[: max(1, self.inner_width - 1)] + "…"
            markup = escape(plain)
        if style:
            markup = f"[{style}]{markup}[/{style}]"
        self.lines.append((False, markup, plain))

    def add_row(self, label: str, value_markup: str, value_plain: str = None,
                label_width: int = 8) -> None:
        """A bold label followed by a value that may carry its own styling.

        `value_plain` is the visible text; pass it when known so an
        overflowing value is clipped from the plain text rather than having its
        markup escaped and shown literally.
        """
        if value_plain is None:
            value_plain = visible_length_text(value_markup)
        # Always leave at least one space so a full-width label cannot collide
        # with its value.
        gap = " " * max(1, label_width - len(label))
        self.add(f"[bold white]{escape(label)}[/bold white]{gap}{value_markup}",
                 plain=f"{label}{gap}{value_plain}")

    def rule(self) -> None:
        """A full-width light rule between two sections."""
        self.lines.append((True, "", ""))

    def top(self, title: str = "", right: str = "") -> str:
        """Top border. ``title`` is plain text; ``right`` may carry markup."""
        title = _clip(title, self.width - 4)
        right_plain = visible_length_text(right) if right else ""
        budget = self.width - 4 - len(title) - 1
        if len(right_plain) > budget:
            right = escape(right_plain[: max(0, budget - 1)] + "…")
            right_plain = right_plain[: max(0, budget - 1)] + "…"
        if right:
            fill = max(1, self.width - 4 - len(title) - len(right_plain))
            middle = f"{FRAME_H}{escape(title)}{FRAME_H * fill}{right}{FRAME_H}"
        else:
            middle = f"{FRAME_H}{escape(title)}{FRAME_H * (self.width - 3 - len(title))}"
        return f"[{self.border}]{FRAME_TL}{middle}{FRAME_TR}[/{self.border}]"

    def bottom(self) -> str:
        return (f"[{self.border}]{FRAME_BL}{FRAME_H * (self.width - 2)}"
                f"{FRAME_BR}[/{self.border}]")

    def frame(self, title: str = "", right: str = "") -> list:
        """The finished panel as a list of lines, frame included."""
        edge = f"[{self.border}]{FRAME_V}[/{self.border}]"
        lines = [self.top(title, right)]
        for is_rule, markup, plain in self.lines:
            if is_rule:
                lines.append(f"{edge}[{self.border}]{LIGHT_H * (self.width - 2)}[/{self.border}]{edge}")
            else:
                slack = max(0, self.inner_width - len(plain))
                lines.append(f"{edge} {markup}{' ' * slack} {edge}")
        lines.append(self.bottom())
        return lines
