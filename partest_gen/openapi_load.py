"""Load OpenAPI documents from local path or URL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from partest_gen._text import redact_source
from partest_gen.ir import SuiteIR, build_ir_from_openapi_dict


class SpecReadError(ValueError):
    """The specification cannot become a suite, for a reason this module diagnosed itself.

    ``stage`` says where it failed: ``"fetch"`` — the URL cannot be requested (credentials
    that are not Latin-1); ``"read"`` — a downloaded body cannot be decoded (a charset
    Python does not know, bytes that are not that charset, UTF-16 the ``Content-Type`` does
    not announce); ``"shape"`` — the text is not a specification (an HTML or XML page, a top
    level that is not a mapping, ``info`` or ``paths`` that holds a value but not a mapping).
    ``downloaded`` is true when the source is a URL, so a caller can suggest downloading the
    file and passing it instead.

    A ``ValueError`` subclass, so ``except ValueError`` keeps catching it. The message names
    the problem, never the source — a source can be a URL with credentials in it; the caller
    knows what it asked for. Other failures keep their own types: ``FileNotFoundError``,
    ``OSError``, ``UnicodeDecodeError`` (a local file), ``json.JSONDecodeError``,
    ``yaml.YAMLError`` and the exceptions of ``requests`` and ``urllib3``.
    """

    def __init__(self, message: str, *, downloaded: bool = False, stage: str = "shape") -> None:
        super().__init__(message)
        self.downloaded = downloaded
        self.stage = stage


def _clip(text: str, limit: int = 40) -> str:
    """A header value as a message may quote it: short, so a server cannot flood the line."""
    return text if len(text) <= limit else text[:limit] + "…"


def _decode_response(content: bytes, content_type: str) -> str:
    """The body as text: the declared charset, else UTF-8 with an optional BOM. A body that
    cannot be decoded is a :class:`SpecReadError` at the ``read`` stage."""
    charset = _charset(content_type)
    named = "UTF-8" if charset == "utf-8-sig" else _clip(charset)
    try:
        return content.decode(charset).lstrip("\ufeff")
    except LookupError:
        raise SpecReadError(
            f"the response declares a charset Python does not know ({named!r})",
            downloaded=True,
            stage="read",
        ) from None
    except UnicodeDecodeError as exc:
        family = charset.lower().replace("_", "-")
        announced = family.startswith(("utf-16", "utf16", "utf-32", "utf32"))
        if content[:2] in (b"\xff\xfe", b"\xfe\xff") and not announced:
            message = "the response is UTF-16 text and its Content-Type does not say so"
        else:
            message = (
                f"the response is not valid {named} text "
                f"(byte 0x{content[exc.start]:02x} at offset {exc.start})"
            )
        raise SpecReadError(message, downloaded=True, stage="read") from None
    except UnicodeError:  # a codec that cannot decode at all ("undefined", "idna")
        raise SpecReadError(
            f"the response cannot be decoded as {named}", downloaded=True, stage="read"
        ) from None


def _charset(content_type: str) -> str:
    """The ``charset=`` a response declares, or ``utf-8-sig`` when it declares none."""
    import re

    match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", content_type, re.I)
    if match is None or match.group(1).lower().replace("_", "-") in {"utf-8", "utf8"}:
        return "utf-8-sig"  # a BOM is accepted either way
    return match.group(1)


class _SpecLoader(yaml.SafeLoader):
    """``yaml.SafeLoader`` whose values that cannot be built are ``yaml.YAMLError`` too.

    The safe constructor turns ``2023-02-29`` or ``2023-13-01`` into a ``datetime.date`` and
    lets the ``ValueError`` of an impossible date escape bare — no line, and a type a caller
    cannot tell from a bug. Here it is a ``ConstructorError`` at the value's position.
    """

    def construct_object(self, node, deep=False):
        try:
            return super().construct_object(node, deep=deep)
        except (ValueError, AttributeError) as exc:
            # The text of the error repeats the value (``invalid literal for int() with base
            # 10: '…'``): only the part before the colon is kept, and the value is clipped.
            # AttributeError is what ``!!timestamp zzz`` gives: the pattern did not match.
            if isinstance(exc, ValueError):
                reason = str(exc).split(":", 1)[0].strip()
            else:
                reason = "not a value its tag can hold"
            scalar = isinstance(node, yaml.ScalarNode)
            what = f"cannot read the value {_clip(str(node.value))!r}" if scalar else (
                "cannot read a value"
            )
            advice = ""
            if isinstance(exc, ValueError) and str(node.tag).endswith(":timestamp"):
                advice = "; quote it to keep it a string"
            raise yaml.constructor.ConstructorError(
                None, None, f"{what}: {reason}{advice}", node.start_mark
            ) from None


def _yaml_load(text: str) -> Any:
    # _SpecLoader inherits SafeLoader; it only turns a ValueError or AttributeError raised
    # while building a value into a ConstructorError.
    return yaml.load(text, Loader=_SpecLoader)  # nosec B506


def _is_url(src: str) -> bool:
    """Whether *src* is fetched rather than opened: an ``http``/``https`` scheme, any case."""
    return src.strip().lower().startswith(("http://", "https://"))


def _a(value: Any) -> str:
    name = type(value).__name__
    return f"{'an' if name[:1] in 'aeiou' else 'a'} {name}"


def load_openapi_dict(source: Union[str, Path], *, source_type: str = "auto") -> Dict[str, Any]:
    """Load OpenAPI YAML/JSON from file path or HTTP(S) URL.

    Parameters
    ----------
    source:
        Local path or URL.
    source_type:
        ``local`` | ``url`` | ``auto`` (detect by scheme, in any case).

    A local file is decoded as UTF-8, a byte order mark accepted. A downloaded body is
    decoded with the ``charset=`` its ``Content-Type`` declares, else the same way.
    :class:`SpecReadError` is raised with ``stage="fetch"`` for credentials in the URL that
    are not Latin-1 (requests cannot send them); with ``stage="read"`` for a body that cannot
    be decoded; and with ``stage="shape"`` for a body that starts with ``<`` — an HTML or XML
    page, told by the body and not by the ``Content-Type`` — and for a top level that is not
    a mapping.
    """
    src = str(source)
    kind = source_type
    if kind == "auto":
        kind = "url" if _is_url(src) else "local"

    if kind == "url":
        import requests

        try:
            resp = requests.get(src.strip(), timeout=60)
        except UnicodeError:
            # requests encodes Basic credentials as Latin-1; its error quotes the character.
            # Only the request itself is guarded: nothing of the generator runs in here.
            raise SpecReadError(
                "credentials in the URL are not Latin-1; percent-encode them",
                downloaded=True,
                stage="fetch",
            ) from None
        resp.raise_for_status()
        # Not resp.text: for text/* without a charset requests decodes as ISO-8859-1, which
        # turns a BOM and every non-ASCII character into mojibake. A declared charset wins.
        text = _decode_response(resp.content, resp.headers.get("Content-Type", ""))
        # By the body, not the Content-Type: a specification served as text/html is still a
        # specification, and a login page served as text/plain is not one.
        if text.lstrip().startswith("<"):
            raise SpecReadError(
                "the URL returned an HTML or XML page (a login or error page?), "
                "not a specification",
                downloaded=True,
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _yaml_load(text)
    elif kind == "local":
        path = Path(src)
        if not path.is_file():
            raise FileNotFoundError(f"OpenAPI file not found: {redact_source(src)}")
        # utf-8-sig: an editor that saves "UTF-8 with BOM" produces a valid document, and
        # json.loads refuses the mark.
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            try:
                data = _yaml_load(text)
            except Exception:
                data = json.loads(text)
    else:
        raise ValueError("source_type must be local, url, or auto")

    if not isinstance(data, dict):
        raise SpecReadError(
            f"its top level is {'empty' if data is None else _a(data)}, not a mapping",
            downloaded=kind == "url",
        )
    return data


def _check_openapi_shape(data: Dict[str, Any], *, downloaded: bool = False) -> None:
    """Raise :class:`SpecReadError` where building the suite would fail on the shape.

    Only what the IR builder relies on: ``info`` and ``paths``, when given a value, must be
    mappings. An empty value (``[]``, ``""``, ``0``) reads as absent, and a missing
    ``openapi``/``swagger`` field is accepted.
    """
    for key in ("info", "paths"):
        value = data.get(key)
        if value and not isinstance(value, dict):
            raise SpecReadError(f"'{key}' is {_a(value)}, not a mapping", downloaded=downloaded)


def load_openapi(source: Union[str, Path], *, source_type: str = "auto") -> SuiteIR:
    """Load OpenAPI and return SuiteIR. ``SuiteIR.source`` is the source with any URL
    credentials, query string and fragment removed."""
    data = load_openapi_dict(source, source_type=source_type)
    downloaded = source_type == "url" or (source_type == "auto" and _is_url(str(source)))
    _check_openapi_shape(data, downloaded=downloaded)
    return build_ir_from_openapi_dict(data, source=str(source))
