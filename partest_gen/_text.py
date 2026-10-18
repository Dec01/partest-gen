"""Text from the specification, made safe to show: in a terminal and in Markdown.

The specification is outside input. Controls, bidi overrides, zero-width characters, line
and paragraph separators and lone surrogates in it would otherwise reorder or hide what a
generated file or a console line says.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that change how text is displayed or where a line ends without being visible.
_INVISIBLE = {"Cc", "Cf", "Zl", "Zp", "Cs"}


def visible(value: object) -> str:
    """``value`` with every invisible or control character written as a ``\\uXXXX`` escape.
    Printable text, non-ASCII included, is unchanged."""
    out = []
    for ch in str(value):
        if unicodedata.category(ch) in _INVISIBLE:
            code = ord(ch)
            out.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            out.append(ch)
    return "".join(out)


def md_text(value: object) -> str:
    """Text for a Markdown table cell or heading: invisible characters escaped, ``|`` escaped
    so it cannot split a table row."""
    return visible(value).replace("|", "\\|")


def md_code(value: object) -> str:
    """Text as a Markdown code span that its own backticks cannot close."""
    text = md_text(value)
    if "`" not in text:
        return f"`{text}`"
    fence = "`" * (max(len(run) for run in re.findall(r"`+", text)) + 1)
    return f"{fence} {text} {fence}"
