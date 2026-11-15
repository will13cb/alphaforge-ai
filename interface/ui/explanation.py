"""Display hierarchy for saved, live and template explanations; no content generation."""
from __future__ import annotations

import re


def format_explanation(text: str, strategies: list[dict] | None = None) -> str:
    """Promote section labels and strategy names to semantic Markdown headings.

    Formatting happens only for display, so model facts, validation, cache keys,
    audit records and read-aloud text remain unchanged.
    """
    names = {s["name"].rstrip(".:") for s in strategies or [] if s.get("name")}
    lines = []
    for line in text.splitlines():
        bold = re.match(r"^\s*(?P<bullet>[-*]\s+)?\*\*(?P<title>.+?)\*\*(?P<rest>.*)$", line)
        italic = re.match(r"^\s*\*(?!\*)(?P<title>[^*]+)\*(?P<rest>.*)$", line)
        match = bold or italic
        if match:
            title = match["title"].strip().rstrip(".:")
            is_strategy = title in names
            if bold or is_strategy:
                rest = match["rest"].lstrip(" .:")
                lines += ["", f"{'####' if is_strategy else '###'} {title}", ""]
                if rest:
                    lines += [rest, ""]
                continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
