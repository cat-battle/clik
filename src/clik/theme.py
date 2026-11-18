"""Colors and small Rich renderables shared by the CLI and the TUI."""

from zlib import crc32

from rich.text import Text

from clik.models import COLOR_NAMES, Card, Priority, Tag

PRIORITY_COLORS = {
    Priority.NONE: "#6c7086",
    Priority.LOW: "#a6e3a1",
    Priority.MEDIUM: "#f9e2af",
    Priority.HIGH: "#fab387",
    Priority.URGENT: "#f38ba8",
}
_PALETTE = list(COLOR_NAMES.values())
DIM = "#7f849c"
OK = "#a6e3a1"
WARN = "#f38ba8"


def tag_color(tag: Tag) -> str:
    """The tag's pinned color, or a stable one derived from its name."""
    return tag.color or _PALETTE[crc32(tag.name.encode()) % len(_PALETTE)]


def tag_chips(tags: tuple[Tag, ...]) -> Text:
    text = Text()
    for i, tag in enumerate(tags):
        if i:
            text.append(" ")
        text.append(f" {tag.name} ", style=f"#11111b on {tag_color(tag)}")
    return text


def priority_text(priority: Priority) -> Text:
    return Text(priority.label, style=f"bold {PRIORITY_COLORS[priority]}")


def checklist_progress(card: Card, width: int = 8) -> Text:
    """e.g. `3/5 ━━━━━───`; empty when the card has no checklist."""
    total = len(card.checklist)
    if not total:
        return Text()
    done = card.checks_done
    filled = round(width * done / total)
    color = OK if done == total else PRIORITY_COLORS[Priority.MEDIUM]
    text = Text(f"{done}/{total} ", style=color)
    text.append("━" * filled, style=color)
    text.append("─" * (width - filled), style=DIM)
    return text
