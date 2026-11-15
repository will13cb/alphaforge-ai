"""Readability for saved prose answers: whitespace only, without rewriting checked facts."""
from __future__ import annotations

import re


def readable_markdown(text: str) -> str:
    """Keep authored Markdown intact; break long legacy prose into short paragraphs.

    Splits only existing whitespace after sentence punctuation, never decimals, signs,
    amounts, tickers or wording. Voice playback and trace history retain the original text.
    """
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for block in blocks:
        if len(block) < 280 or "\n" in block or re.search(r"(^\s*[#>*|\-]|\*\*|`|\[[^]]+\]\()", block):
            out.append(block)
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ\"'‘“])", block)
        paragraph = ""
        for sentence in sentences:
            if paragraph and len(paragraph) + len(sentence) > 240:
                out.append(paragraph)
                paragraph = sentence
            else:
                paragraph += (" " if paragraph else "") + sentence
        if paragraph:
            out.append(paragraph)
    return "\n\n".join(out)
