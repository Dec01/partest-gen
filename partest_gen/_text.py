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


# A scheme as RFC 3986 spells it, in any case, possibly with whitespace around the source.
_SCHEME = re.compile(r"^\s*([A-Za-z][A-Za-z0-9+.\-]*)://(.*)$", re.S)

#: What a source that looks like a URL but cannot be cleaned is shown as.
URL_NOT_SHOWN = "<URL not shown>"


def redact_source(source: object) -> str:
    """A specification source fit to show and to store: a URL loses credentials, query and
    fragment; anything without ``://`` — a local path, a mistyped scheme — is returned as it
    is.

    Anything with ``://`` is a URL, whatever its scheme, its case or the whitespace around
    it. Its authority is the text up to the first ``/``, ``?`` or ``#``; credentials in it,
    up to its last ``@``, become ``***@``. Query and fragment always go.

    An ``@`` after the authority is ambiguous: ``/npm/@scope/pkg@1.0/`` on a CDN, or the rest
    of a password with an unencoded ``/``, ``?`` or ``#`` (``admin:2024/q@host``,
    ``tok/en@github.com``). Ambiguity is settled towards hiding: the URL is shown as
    ``<URL not shown>`` when the authority carries credentials and another ``@`` follows
    it anywhere (``u:pa@ss.word/x@h.test``), when an ``@`` follows the authority and its host
    has a ``:`` (a port included) or is a name without a dot that is not an IPv6 literal,
    and when the host after a userinfo ``@`` has a ``:`` not followed by a number. A dotted
    host without a port and without credentials — ``cdn.jsdelivr.net/npm/@acme/spec@2.1.0``
    — stays visible.

    Never raises: a failure here would print the raw source in a traceback, so it is shown
    as ``<URL not shown>`` instead. Not ``urlsplit``, which raises on some malformed URLs.
    Applying it twice gives the same text. A token inside the path itself cannot be told
    apart and stays.
    """
    text = str(source)
    if "://" not in text:
        return text
    try:
        return _redact_url(text)
    except Exception:
        return URL_NOT_SHOWN


def _ambiguous_host(host: str, at_later: bool) -> bool:
    """Whether *host* (authority without userinfo) could be the cut-off rest of a secret."""
    literal, closed, after = host.partition("]") if host.startswith("[") else ("", "", host)
    if closed:  # an IPv6 literal: only what follows "]" can be a port
        colon, dotless = ":" in after, False
        port = after[1:] if after.startswith(":") else ("" if not after else None)
    else:
        name, colon_mark, port = host.partition(":")
        colon, dotless = bool(colon_mark), "." not in name
    if colon and not (port or "").isdigit():
        return True
    return at_later and (colon or dotless)


def _redact_url(text: str) -> str:
    match = _SCHEME.match(text)
    if match is None:
        return URL_NOT_SHOWN
    scheme, rest = match.group(1), match.group(2).strip()
    end = re.search(r"[/?#]", rest)
    authority, tail = (rest[: end.start()], rest[end.start():]) if end else (rest, "")
    at_later = "@" in tail
    userinfo, at, host = authority.rpartition("@")
    if at and at_later:
        # credentials, and another @ further on: which @ ends the password cannot be known
        return URL_NOT_SHOWN
    if _ambiguous_host(host, at_later) and (at or at_later):
        return URL_NOT_SHOWN
    path = re.split(r"[?#]", tail, maxsplit=1)[0]
    return f"{scheme}://{'***@' if at else ''}{host}{path}"
