"""The command line surface: subcommands, and the version a bug report needs.

The emitters have their own tests. This file covers the layer above them — that a command
exists, parses what it claims to parse, and reports the right thing on bad input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from partest_gen import __version__
from partest_gen.cli import build_parser, main as cli_main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_version_flag_reports_the_package_version(capsys):
    """A generated tree carries no version; the CLI is the only way to ask which one wrote it."""
    with pytest.raises(SystemExit) as exit_info:
        cli_main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_every_documented_command_is_registered():
    """The skill and the wiki name these; a rename must break here, not in someone's terminal."""
    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None) and hasattr(a, "_name_parser_map")]
    assert actions, "no subparsers found"
    commands = set(actions[0].choices)
    assert commands == {
        "init",
        "init-ui",
        "from-openapi",
        "sync-openapi",
        "dump-ir",
        "init-package-exports",
    }


def test_init_package_exports_writes_reexports(tmp_path: Path):
    pkg = tmp_path / "res"
    pkg.mkdir()
    (pkg / "paths.py").write_text("P=1\n", encoding="utf-8")

    assert cli_main(["init-package-exports", str(pkg), "-v"]) == 0
    assert "from .paths import *" in (pkg / "__init__.py").read_text(encoding="utf-8")


def test_dump_ir_writes_json_without_touching_a_project(tmp_path: Path):
    """The one command that is safe to run against a directory you care about."""
    out = tmp_path / "suite_ir.json"
    assert cli_main(["dump-ir", str(FIXTURE), "-o", str(out)]) == 0
    assert out.is_file()
    assert out.read_text(encoding="utf-8").strip().startswith("{")
    assert list(tmp_path.iterdir()) == [out], "dump-ir must write only the file it was asked for"


@pytest.mark.parametrize("where", ["under a file", "a directory"])
def test_dump_ir_to_a_path_it_cannot_write_is_one_line_and_exit_code_2(where, tmp_path, capsys):
    """The output path is the user's input as much as the specification is."""
    blocker = tmp_path / "blocker"
    if where == "under a file":
        blocker.write_text("x", encoding="utf-8")
        out = blocker / "ir.json"
    else:
        blocker.mkdir()
        out = blocker
    capsys.readouterr()
    code = cli_main(["dump-ir", str(FIXTURE), "-o", str(out)])
    captured = capsys.readouterr()
    assert code == 2
    assert "Traceback" not in captured.err
    lines = captured.err.strip().splitlines()
    assert len(lines) == 1, captured.err
    assert lines[0].startswith(f"error: cannot write IR to {out}: ")
    assert "Wrote IR" not in captured.out


def test_dump_ir_that_fails_to_write_keeps_the_previous_file(tmp_path, monkeypatch, capsys):
    """Written through a temporary file and ``os.replace``: no truncated IR, no leftovers."""
    import os

    out = tmp_path / "ir.json"
    out.write_text("previous", encoding="utf-8")

    def refuse(src, dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", refuse)
    assert cli_main(["dump-ir", str(FIXTURE), "-o", str(out)]) == 2
    assert "Permission denied" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.iterdir()) == [out], "the temporary file must not stay behind"


def test_sync_without_a_project_fails_instead_of_creating_one(tmp_path: Path, capsys):
    """A typo in the path must not silently scaffold a project somewhere unexpected."""
    missing = tmp_path / "not-here"
    code = cli_main(["sync-openapi", str(missing), "--file", str(FIXTURE)])
    assert code != 0
    assert not missing.exists()
    assert "not found" in capsys.readouterr().err


# --- a specification that cannot be read: one line, exit code 2 -------------------------------

_COMMANDS = ["from-openapi", "sync-openapi", "dump-ir", "init"]


def _argv(command: str, tmp_path: Path, source: str, *, url: bool = False):
    """Each command that reads a specification, pointed at *source*."""
    project = tmp_path / "proj"
    if command == "from-openapi":
        return [command, str(project), "--url" if url else "--file", source]
    if command == "sync-openapi":
        project.mkdir(exist_ok=True)  # an existing project: the spec is what fails
        return [command, str(project), "--url" if url else "--file", source]
    if command == "dump-ir":
        return [command, source]
    return [command, str(project), "--openapi", source]


def _spec_file(tmp_path: Path, name: str, content) -> str:
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return str(path)


def _one_line_and_two(command, tmp_path, source, capsys, *, url=False):
    capsys.readouterr()
    code = cli_main(_argv(command, tmp_path, source, url=url))
    err = capsys.readouterr().err
    assert code == 2
    assert "Traceback" not in err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    if command != "sync-openapi":
        assert not (tmp_path / "proj").exists(), "nothing may be written for an unreadable spec"
    return lines[0]


_BAD_FILES = {
    "missing": (None, "not found"),
    "not utf-8": (("spec.yaml", b"openapi: 3.0.0\ninfo: {title: \xff\xfe}\n"), "not UTF-8 text"),
    "invalid yaml": (("spec.yaml", "openapi: 3.0.0\npaths: [unclosed\n"), "is not valid YAML"),
    "invalid json": (("spec.json", '{"openapi": "3.0.0", "paths": '), "is not valid JSON"),
    "a list": (("spec.yaml", "- a\n- b\n"), "its top level is a list, not a mapping"),
    "empty": (("spec.yaml", ""), "its top level is empty, not a mapping"),
    "utf-16": (("spec.yaml", "openapi: 3.0.0\n".encode("utf-16")),
               "UTF-16 text — re-save it as UTF-8"),
    "paths not a mapping": (("spec.yaml", "openapi: 3.0.0\npaths: [1, 2]\n"),
                            "'paths' is a list, not a mapping"),
    "info not a mapping": (("spec.yaml", "openapi: 3.0.0\ninfo: just text\npaths: {}\n"),
                           "'info' is a str, not a mapping"),
}


@pytest.mark.parametrize("command", _COMMANDS)
@pytest.mark.parametrize("case", sorted(_BAD_FILES))
def test_an_unreadable_specification_is_one_line_and_exit_code_2(command, case, tmp_path, capsys):
    spec, expected = _BAD_FILES[case]
    source = str(tmp_path / "nope.yaml") if spec is None else _spec_file(tmp_path, *spec)
    line = _one_line_and_two(command, tmp_path, source, capsys)
    assert line.startswith("error: ")
    assert expected in line
    assert Path(source).name in line, "the message names the file"


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_directory_is_not_a_specification(command, tmp_path, capsys):
    folder = tmp_path / "specs"
    folder.mkdir()
    assert "is a directory" in _one_line_and_two(command, tmp_path, str(folder), capsys)


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_specification_without_read_permission(command, tmp_path, capsys, monkeypatch):
    # chmod does not take read permission away on Windows; the error is what matters
    source = _spec_file(tmp_path, "spec.yaml", "openapi: 3.0.0\n")
    real = Path.read_text

    def read_text(self, *a, **k):
        if self.name == "spec.yaml":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", read_text)
    line = _one_line_and_two(command, tmp_path, source, capsys)
    assert "cannot read OpenAPI specification" in line and "Permission denied" in line


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_specification_url_that_cannot_be_fetched(command, tmp_path, capsys, monkeypatch):
    import requests

    from urllib3.exceptions import MaxRetryError, NameResolutionError

    def unreachable(url, **kwargs):
        # what requests raises for a host that does not resolve; every message names the URL
        reason = NameResolutionError("spec.example", None, OSError(f"cannot resolve {url}"))
        raise requests.ConnectionError(MaxRetryError(None, url, reason=reason))

    monkeypatch.setattr(requests, "get", unreachable)
    url = "https://user:s3cret@spec.example/openapi.yaml?token=abc"
    line = _one_line_and_two(command, tmp_path, url, capsys, url=True)
    assert line == (
        "error: cannot fetch OpenAPI specification https://***@spec.example/openapi.yaml: "
        "ConnectionError (NameResolutionError)"
    )


def test_a_specification_url_answering_404(tmp_path, capsys, monkeypatch):
    import requests

    def not_found(url, **kwargs):
        response = requests.Response()
        response.status_code = 404
        response.url = url
        return response

    monkeypatch.setattr(requests, "get", not_found)
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/openapi.yaml", capsys)
    assert line.endswith(": HTTP 404 — download it and pass it with its path instead of the URL")


def _served(monkeypatch, body: bytes, content_type: str, status: int = 200):
    import requests

    def get(url, **kwargs):
        response = requests.Response()
        response.status_code = status
        response._content = body
        response.headers["Content-Type"] = content_type
        response.url = url
        return response

    monkeypatch.setattr(requests, "get", get)


@pytest.mark.parametrize("status", [401, 403])
def test_a_specification_url_behind_a_login(status, tmp_path, capsys, monkeypatch):
    _served(monkeypatch, b"", "text/plain", status=status)
    line = _one_line_and_two(
        "from-openapi", tmp_path, "https://spec.example/o.yaml", capsys, url=True
    )
    assert line.endswith(f": HTTP {status} — download it and pass it with --file <path>")


@pytest.mark.parametrize("content_type", ["text/html; charset=utf-8", "text/plain"])
def test_an_html_page_is_not_a_specification(content_type, tmp_path, capsys, monkeypatch):
    """Told by the body, whatever the Content-Type claims."""
    _served(monkeypatch, b"\xef\xbb\xbf  \n<!doctype html><body>Sign in</body>", content_type)
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert line == (
        "error: https://spec.example/o.yaml is not an OpenAPI document: the URL returned an "
        "HTML or XML page (a login or error page?), not a specification — download it and "
        "pass it with its path instead of the URL"
    )


def test_a_specification_served_as_html_is_read(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, b"openapi: 3.0.0\ninfo: {title: html}\npaths: {}\n", "text/html")
    assert cli_main(["dump-ir", "https://spec.example/o.yaml"]) == 0
    assert '"title": "html"' in capsys.readouterr().out


def test_a_declared_charset_is_honoured(tmp_path, capsys, monkeypatch):
    body = "openapi: 3.0.0\ninfo: {title: Каталог}\npaths: {}\n".encode("cp1251")
    _served(monkeypatch, body, 'text/yaml; charset="windows-1251"')
    assert cli_main(["dump-ir", "https://spec.example/o.yaml"]) == 0
    assert '"title": "Каталог"' in capsys.readouterr().out


def test_utf16_without_a_charset_from_a_url(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, "openapi: 3.0.0\n".encode("utf-16"), "text/plain")
    line = _one_line_and_two("from-openapi", tmp_path, "https://spec.example/o.yaml", capsys,
                             url=True)
    assert "the response is UTF-16 text and its Content-Type does not say so" in line
    assert line.endswith("download it and pass it with --file <path>")
    assert "re-save" not in line


def test_utf16_with_its_charset_from_a_url_is_read(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, "openapi: 3.0.0\ninfo: {title: u16}\n".encode("utf-16"),
            "text/plain; charset=utf-16")
    assert cli_main(["dump-ir", "https://spec.example/o.yaml"]) == 0
    assert '"title": "u16"' in capsys.readouterr().out


def test_an_unknown_charset_is_one_line(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, b"openapi: 3.0.0\n", "text/plain; charset=klingon-8")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "klingon-8" in line


def test_a_redirect_loop_names_its_class_not_a_status(tmp_path, capsys, monkeypatch):
    import requests

    def loop(url, **kwargs):
        response = requests.Response()
        response.status_code = 302
        raise requests.TooManyRedirects("Exceeded 30 redirects.", response=response)

    monkeypatch.setattr(requests, "get", loop)
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert line.endswith(
        ": TooManyRedirects — download it and pass it with its path instead of the URL"
    )
    assert "HTTP 302" not in line


def test_a_downloaded_specification_is_decoded_as_utf8(tmp_path, capsys, monkeypatch):
    """text/plain without a charset: requests would take ISO-8859-1 for .text."""
    body = "\ufeffopenapi: 3.0.0\ninfo: {title: Каталог}\npaths: {}\n".encode("utf-8")
    _served(monkeypatch, body, "text/plain")
    assert cli_main(["dump-ir", "https://spec.example/o.yaml"]) == 0
    assert '"title": "Каталог"' in capsys.readouterr().out


@pytest.mark.parametrize("url", ["http://h..example/x.yaml", "http://" + "a" * 70 + ".example/x"])
def test_a_host_urllib3_cannot_parse_is_one_line(url, tmp_path, capsys):
    """urllib3 raises LocationParseError through requests unwrapped; no network is reached."""
    line = _one_line_and_two("dump-ir", tmp_path, url, capsys)
    assert line.startswith("error: cannot fetch OpenAPI specification ")
    assert line.rsplit(": ", 1)[1].startswith("LocationParseError")


def test_a_rejected_certificate_says_why(tmp_path, capsys, monkeypatch):
    import ssl

    import requests
    from urllib3.exceptions import MaxRetryError, SSLError

    def expired(url, **kwargs):
        cert = ssl.SSLCertVerificationError(1, "certificate verify failed")
        cert.verify_message = "certificate has expired"
        raise requests.exceptions.SSLError(MaxRetryError(None, url, reason=SSLError(cert)))

    monkeypatch.setattr(requests, "get", expired)
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "TLS certificate verification failed (certificate has expired)." in line


def test_from_openapi_says_nothing_before_the_specification_is_read(tmp_path, capsys):
    capsys.readouterr()
    assert cli_main(["from-openapi", str(tmp_path / "p"), "--file", str(tmp_path / "no.yaml")]) == 2
    assert capsys.readouterr().out == ""


def test_a_local_file_named_like_a_scheme_is_copied(tmp_path):
    """Only http:// and https:// are URLs; ``http-api.yaml`` is a file."""
    spec = tmp_path / "http-api.yaml"
    spec.write_bytes(FIXTURE.read_bytes())
    dest = tmp_path / "proj"
    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert cli_main(["from-openapi", str(dest), "--file", "http-api.yaml"]) == 0
    finally:
        os.chdir(cwd)
    copied = (dest / "docs/openapi.yaml").read_text(encoding="utf-8")
    assert copied == spec.read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["info", "paths"])
@pytest.mark.parametrize("empty", ["[]", '""', "false", "0", "{}", "null"])
def test_an_empty_info_or_paths_is_read_as_absent(key, empty, tmp_path, capsys):
    """1.2.0 read these: the IR builder takes a false value for a missing one."""
    lines = ["openapi: 3.0.0", f"{key}: {empty}"]
    if key == "info":
        lines.append("paths: {}")
    source = _spec_file(tmp_path, "spec.yaml", "\n".join(lines) + "\n")
    assert cli_main(["dump-ir", source]) == 0


def test_a_shape_error_names_the_type_with_its_article(tmp_path, capsys):
    source = _spec_file(tmp_path, "spec.yaml", "openapi: 3.0.0\npaths: 7\n")
    assert "'paths' is an int, not a mapping" in _one_line_and_two("dump-ir", tmp_path, source, capsys)


def test_a_generator_bug_behind_a_readable_specification_still_raises(monkeypatch):
    """Only the input is turned into a message; an exception while building the IR is ours."""
    import partest_gen.openapi_load

    def broken(*args, **kwargs):
        raise RuntimeError("emitter bug")

    monkeypatch.setattr(partest_gen.openapi_load, "build_ir_from_openapi_dict", broken)
    with pytest.raises(RuntimeError, match="emitter bug"):
        cli_main(["dump-ir", str(FIXTURE)])


def test_load_openapi_raises_the_parse_errors_the_generator_page_documents(tmp_path, monkeypatch):
    """docs/wiki/components/generator.md §5: a local file that parses as neither YAML nor JSON
    is a ``json.JSONDecodeError`` (a ``ValueError``) with the YAML error as its context; a
    downloaded body is ``yaml.YAMLError`` — not a ``ValueError``."""
    import json

    import yaml

    from partest_gen.openapi_load import load_openapi

    def contexts(exc):
        while exc is not None:
            yield exc
            exc = exc.__context__

    broken = "openapi: 3.0.0\npaths: [unclosed\n"
    with pytest.raises(json.JSONDecodeError) as local:
        load_openapi(_spec_file(tmp_path, "spec.yaml", broken))
    # json's own StopIteration sits between the two
    assert any(isinstance(e, yaml.YAMLError) for e in contexts(local.value))
    with pytest.raises(json.JSONDecodeError) as local_json:
        load_openapi(_spec_file(tmp_path, "spec.json", '{"openapi": '))
    assert not any(isinstance(e, yaml.YAMLError) for e in contexts(local_json.value)), (
        "a .json file is not tried as YAML"
    )

    _served(monkeypatch, broken.encode("utf-8"), "application/yaml")
    with pytest.raises(yaml.YAMLError) as downloaded:
        load_openapi("https://spec.example/o.yaml")
    assert not isinstance(downloaded.value, ValueError)


_IMPOSSIBLE_DATE = "\n".join([
    "openapi: 3.0.0",
    "info: {title: t, version: '1'}",
    "paths:",
    "  /x:",
    "    get:",
    "      responses:",
    "        '200':",
    "          description: ok",
    "          content:",
    "            application/json:",
    "              example: 2023-02-29",
    "",
])


@pytest.mark.parametrize(
    "tag", ["!!python/object/apply:os.system ['echo PWNED']", "!!python/object:builtins.dict {}"]
)
def test_the_spec_loader_stays_safe(tag):
    """``_SpecLoader`` is a SafeLoader: Python tags are still refused, nothing is built."""
    import yaml

    from partest_gen.openapi_load import _SpecLoader, _yaml_load

    assert issubclass(_SpecLoader, yaml.SafeLoader)
    with pytest.raises(yaml.constructor.ConstructorError, match="could not determine a constructor"):
        _yaml_load(f"x: {tag}\n")


@pytest.mark.parametrize("command", _COMMANDS)
def test_a_date_that_does_not_exist_is_one_line_with_its_position(command, tmp_path, capsys):
    """YAML reads an unquoted 2023-02-29 as a date, and the date cannot be built. The safe
    constructor let that out as a bare ValueError: a local file was reported as invalid JSON."""
    source = _spec_file(tmp_path, "spec.yaml", _IMPOSSIBLE_DATE)
    line = _one_line_and_two(command, tmp_path, source, capsys)
    assert line.endswith(
        "is not valid YAML: cannot read the value '2023-02-29': day is out of range for month; "
        "quote it to keep it a string (line 11, column 24)"
    ), line


def test_a_downloaded_date_that_does_not_exist_is_one_line(tmp_path, capsys, monkeypatch):
    """From a URL the same value was a traceback with exit code 1."""
    _served(monkeypatch, _IMPOSSIBLE_DATE.encode("utf-8"), "application/yaml")
    line = _one_line_and_two("from-openapi", tmp_path, "https://spec.example/o.yaml", capsys,
                             url=True)
    assert line == (
        "error: https://spec.example/o.yaml is not valid YAML: cannot read the value "
        "'2023-02-29': day is out of range for month; quote it to keep it a string "
        "(line 11, column 24)"
    )


def test_a_downloaded_specification_left_as_the_placeholder_is_named(tmp_path, capsys,
                                                                      monkeypatch):
    """--url does not save the document; the placeholder is what coverage and a bare sync read."""
    spec = FIXTURE.read_bytes()
    _served(monkeypatch, spec, "application/yaml")
    dest = tmp_path / "proj"
    capsys.readouterr()
    assert cli_main(["from-openapi", str(dest), "--url", "https://spec.example/o.yaml"]) == 0
    out = capsys.readouterr().out
    assert "Not saved: the specification was downloaded, and docs/openapi.yaml is still the" in out
    assert cli_main(["sync-openapi", str(dest), "--url", "https://spec.example/o.yaml"]) == 0
    assert "Not saved:" in capsys.readouterr().out

    (dest / "docs" / "openapi.yaml").write_bytes(spec)  # saved by hand: the hint stops
    assert cli_main(["sync-openapi", str(dest), "--url", "https://spec.example/o.yaml"]) == 0
    assert "Not saved:" not in capsys.readouterr().out

    local = tmp_path / "local"
    assert cli_main(["from-openapi", str(local), "--file", str(FIXTURE)]) == 0
    assert "Not saved:" not in capsys.readouterr().out


def test_init_package_exports_help_does_not_point_into_the_generated_tree(capsys):
    """Run over src/api/resources it takes the generator's __init__.py files for good."""
    with pytest.raises(SystemExit):
        cli_main(["init-package-exports", "-h"])
    out = " ".join(capsys.readouterr().out.split())
    assert "e.g. src/api/resources" not in out
    assert "Never a directory the generator writes" in out
    assert "rewritten whole, recursively — commit first" in out
    assert "src/api/utils" not in out, "the skeleton writes src/api/utils itself"


def test_a_mapping_without_an_openapi_field_is_still_accepted(tmp_path, capsys):
    """1.2.0 read such a document, and the IR does not rely on the field."""
    document = "\n".join(["info: {title: t}", "paths:", "  /x:", "    get: {}", ""])
    source = _spec_file(tmp_path, "spec.yaml", document)
    assert cli_main(["dump-ir", source]) == 0
    assert '"path": "/x"' in capsys.readouterr().out


@pytest.mark.parametrize("name", ["spec.yaml", "spec.json"])
def test_a_utf8_byte_order_mark_is_accepted(name, tmp_path, capsys):
    text = '{"openapi": "3.0.0", "info": {"title": "bom"}, "paths": {}}'
    source = _spec_file(tmp_path, name, b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert cli_main(["dump-ir", source]) == 0
    assert '"title": "bom"' in capsys.readouterr().out


@pytest.mark.parametrize(
    "command, hint",
    [
        ("from-openapi", "--file <path>"),
        ("sync-openapi", "--file <path>"),
        ("init", "--openapi <path>"),
        ("dump-ir", "its path instead of the URL"),
    ],
)
def test_a_rejected_certificate_names_the_ways_out(command, hint, tmp_path, capsys, monkeypatch):
    import ssl

    import requests
    from urllib3.exceptions import MaxRetryError, SSLError

    def self_signed(url, **kwargs):
        cert = ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed")
        raise requests.exceptions.SSLError(MaxRetryError(None, url, reason=SSLError(cert)))

    monkeypatch.setattr(requests, "get", self_signed)
    line = _one_line_and_two(command, tmp_path, "https://spec.example/o.yaml", capsys, url=True)
    assert "TLS certificate verification failed" in line
    assert "REQUESTS_CA_BUNDLE=/path/to/ca.pem" in line
    assert hint in line
    assert "PARTEST_TLS_VERIFY does not apply" in line


@pytest.mark.parametrize(
    "url, secret",
    [
        # urlsplit raises on this one — inside the error handler, with the password in it
        ("http://u:pw@[bad/x.yaml?token=T", ("pw", "token=T")),
        # an unencoded / in the password ends the authority early for urlsplit
        ("http://us3r:pa/ssW0rd@host/x.yaml", ("pa/ssW0rd", "ssW0rd")),
        ("http://us3r:pa?ssW0rd@host/x.yaml", ("ssW0rd",)),
        ("http://us3r:pa#ssW0rd@host/x.yaml", ("ssW0rd",)),
        ("HTTP://u:pw@host/x.yaml?t=1", ("u:pw", "t=1")),
        (" http://u:pw@host/x.yaml", ("u:pw",)),
    ],
)
def test_credentials_never_reach_the_message(url, secret, tmp_path, capsys, monkeypatch):
    import requests

    def refused(u, **kwargs):
        raise requests.ConnectionError(f"refused: {u}")

    monkeypatch.setattr(requests, "get", refused)
    capsys.readouterr()
    code = cli_main(["dump-ir", url])
    err = capsys.readouterr().err
    assert code == 2
    assert "Traceback" not in err
    assert len(err.strip().splitlines()) == 1
    for s in secret:
        assert s not in err


def test_redact_source():
    from partest_gen._text import URL_NOT_SHOWN, redact_source

    assert redact_source("https://u:p@h/a.yaml?x=1#f") == "https://***@h/a.yaml"
    assert redact_source("https://h/a.yaml") == "https://h/a.yaml"
    assert redact_source("docs/openapi.yaml") == "docs/openapi.yaml"
    assert redact_source("1x://u:p@h") == URL_NOT_SHOWN
    # a mistyped scheme is a path, and a path is shown as it is
    assert redact_source("http:/u:p@h/a.yaml") == "http:/u:p@h/a.yaml"


@pytest.mark.parametrize(
    "url, shown",
    [
        # an @ in the path or the query is not userinfo: the host is never invented
        ("https://cdn.jsdelivr.net/npm/@acme/api-spec@2.1.0/openapi.yaml",
         "https://cdn.jsdelivr.net/npm/@acme/api-spec@2.1.0/openapi.yaml"),
        ("https://h.example/x.yaml?owner=me@corp.com", "https://h.example/x.yaml"),
        ("https://unpkg.com/lodash@4/", "https://unpkg.com/lodash@4/"),
        ("https://[::1]/npm/@acme/spec.yaml", "https://[::1]/npm/@acme/spec.yaml"),
        # an @ after the authority with a port, or on a dotless host, is ambiguous: hidden
        ("https://host:8443/a@b.yaml", "<URL not shown>"),
        ("http://127.0.0.1:8080/npm/@acme/spec.yaml", "<URL not shown>"),
        ("https://[::1]:8443/a@b.yaml", "<URL not shown>"),
        ("http://admin:2024/q@host/x.yaml", "<URL not shown>"),
        ("https://tok/en@github.com/x.yaml", "<URL not shown>"),
        ("http://u:12/34/x@h", "<URL not shown>"),
        # a password after the userinfo @, cut short by an unencoded /
        ("https://UU@UU:PPPP/@h.test", "<URL not shown>"),
        # an unclosed IPv6 literal used to raise IndexError inside the cleaning
        ("http://[bad/x@y", "<URL not shown>"),
        ("http://[::1/spec?email=a@b&token=SECRET", "<URL not shown>"),
        # a port after credentials is still a port
        ("https://u:p@h.example:8443/x.yaml", "https://***@h.example:8443/x.yaml"),
        ("ftp://u:SECRET@h/x.yaml", "ftp://***@h/x.yaml"),
        # credentials and another @ further on: which @ ends the password is unknowable
        ("http://u:pa@ss.word/x@h.test", "<URL not shown>"),
        ("http://u:p@ss.w?rd@host/spec", "<URL not shown>"),
        ("http://u:Summer@2024.x#1@h/s", "<URL not shown>"),
        ("https://u:p@registry.example/repo/npm/@scope/spec.yaml", "<URL not shown>"),
        # no credentials in the authority: requests sends host + path, nothing secret
        ("https://ZZ.Z//Z@[::1]/", "https://ZZ.Z//Z@[::1]/"),
        # a password with an unencoded / ? # ends the authority early: not shown at all
        ("http://us3r:pa/ssW0rd@host/x.yaml", "<URL not shown>"),
        ("http://us3r:pa?ssW0rd@host/x.yaml", "<URL not shown>"),
        ("http://us3r:pa#ssW0rd@host/x.yaml", "<URL not shown>"),
        ("HTTP://u:pw@h/x.yaml", "HTTP://***@h/x.yaml"),
        ("  https://u:pw@h/x.yaml ", "https://***@h/x.yaml"),
        ("http://u:pw@[bad/x.yaml?token=T", "http://***@[bad/x.yaml"),
        ("http://u:p@ss@h/x.yaml", "http://***@h/x.yaml"),
    ],
)
def test_redact_source_cases(url, shown):
    from partest_gen._text import redact_source

    assert redact_source(url) == shown
    assert redact_source(shown) == shown, "applying it again changes nothing"


def test_the_stored_source_carries_no_credentials(tmp_path, capsys, monkeypatch):
    """suite_ir.json, openapi_summary.md and dump-ir output all show the IR's source."""
    import requests

    def served(url, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = FIXTURE.read_bytes()
        response.encoding = "utf-8"
        return response

    monkeypatch.setattr(requests, "get", served)
    url = "https://user:s3cret@spec.example/openapi.yaml?token=abc#frag"
    dest = tmp_path / "proj"
    assert cli_main(["from-openapi", str(dest), "--url", url]) == 0
    assert cli_main(["dump-ir", url]) == 0
    out = capsys.readouterr().out
    for text in (
        out,
        (dest / ".partest/suite_ir.json").read_text(encoding="utf-8"),
        (dest / ".partest/openapi_summary.md").read_text(encoding="utf-8"),
    ):
        assert "s3cret" not in text and "token=abc" not in text and "frag" not in text
    assert "https://***@spec.example/openapi.yaml" in out


def test_the_recovery_after_init_package_exports_in_the_generated_tree(tmp_path, capsys):
    """The recipe on the generator page, step by step, ends in the tree a fresh run writes."""
    import filecmp
    import shutil

    project = tmp_path / "proj"
    assert cli_main(["from-openapi", str(project), "--file", str(FIXTURE), "--depth", "p1"]) == 0
    fresh = tmp_path / "fresh"
    shutil.copytree(project, fresh)

    assert cli_main(["init-package-exports", str(project / "src/api/resources")]) == 0
    banner = "# AUTO-GENERATED by partest.tools.generate_init"
    taken = [
        p for p in (project / "src/api/resources").rglob("__init__.py")
        if p.read_text(encoding="utf-8").startswith(banner)
    ]
    assert taken, "init-package-exports wrote nothing — the scenario did not happen"
    for p in taken:
        p.unlink()
    assert cli_main(["sync-openapi", str(project), "--file", str(FIXTURE), "--depth", "p1"]) == 0
    assert cli_main(["init", str(project)]) == 0

    def files(root):
        return sorted(
            str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )

    assert files(project) == files(fresh)
    _, mismatch, errors = filecmp.cmpfiles(project, fresh, files(fresh), shallow=False)
    assert not mismatch and not errors, mismatch + errors


def test_a_failure_inside_the_cleaning_never_shows_the_source(monkeypatch):
    import partest_gen._text as text

    def broken(_):
        raise RuntimeError("bug in the cleaning")

    monkeypatch.setattr(text, "_redact_url", broken)
    assert text.redact_source("https://u:SECRET@h.example/x.yaml") == text.URL_NOT_SHOWN


def test_a_missing_file_with_a_scheme_is_named_without_its_secret(tmp_path):
    """Path() collapses :// to :/, so the message must clean the string, not the Path."""
    from partest_gen.openapi_load import load_openapi

    with pytest.raises(FileNotFoundError) as info:
        load_openapi("ftp://u:SECRET@h/x.yaml")
    assert "SECRET" not in str(info.value)
    assert "ftp://***@h/x.yaml" in str(info.value)


def test_an_ir_without_a_source_keeps_none():
    from partest_gen.ir import build_ir_from_openapi_dict

    assert build_ir_from_openapi_dict({"paths": {}}, source=None).source is None
    assert build_ir_from_openapi_dict({"paths": {}}).source == ""


def test_credentials_that_are_not_latin1(tmp_path, capsys):
    """requests encodes Basic credentials as Latin-1; its error quotes the character."""
    line = _one_line_and_two("dump-ir", tmp_path, "http://u:passж@h.test/x.yaml", capsys)
    assert line == (
        "error: cannot fetch OpenAPI specification http://***@h.test/x.yaml: credentials in "
        "the URL are not Latin-1; percent-encode them — download it and pass it with its "
        "path instead of the URL"
    )
    assert "ж" not in line and "pass" not in line.split("them")[0]


@pytest.mark.parametrize("charset", ["undefined", "idna", "klingon-8", "x" * 200])
def test_a_charset_that_cannot_decode_is_one_line(charset, tmp_path, capsys, monkeypatch):
    _served(monkeypatch, b"openapi: 3.0.0\n\xe9\n", f"text/plain; charset={charset}")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert line.startswith("error: cannot read OpenAPI specification https://spec.example/o.yaml: ")
    assert line.endswith("download it and pass it with its path instead of the URL")
    assert len(line) < 260, "a header value must not flood the line"


def test_utf16_under_a_utf8_charset(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, "openapi: 3.0.0\n".encode("utf-16"), "text/yaml; charset=utf-8")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "the response is UTF-16 text and its Content-Type does not say so" in line


def test_bytes_outside_the_declared_charset_name_it(tmp_path, capsys, monkeypatch):
    _served(monkeypatch, "openapi: 3.0.0\ninfo: {title: é}\n".encode("utf-8"),
            "text/yaml; charset=us-ascii")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "the response is not valid us-ascii text (byte 0xc3 at offset" in line
    assert "UTF-8" not in line


@pytest.mark.parametrize("body", [b"", b"Unauthorized", b"openapi: 3.0.0\npaths: [1]\n"])
def test_a_downloaded_non_specification_suggests_the_file(body, tmp_path, capsys, monkeypatch):
    """An SSO answering 200 with an empty body or a word is common."""
    _served(monkeypatch, body, "text/plain")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "is not an OpenAPI document" in line
    assert line.endswith("download it and pass it with its path instead of the URL")


def test_a_generator_bug_behind_a_url_still_raises(monkeypatch):
    """Errors of the codec become a line; a KeyError of the generator does not."""
    import partest_gen.openapi_load

    _served(monkeypatch, FIXTURE.read_bytes(), "text/yaml")

    def broken(*args, **kwargs):
        raise KeyError("emitter bug")

    monkeypatch.setattr(partest_gen.openapi_load, "build_ir_from_openapi_dict", broken)
    with pytest.raises(KeyError, match="emitter bug"):
        cli_main(["dump-ir", "https://spec.example/o.yaml"])


def test_a_broken_body_under_an_announced_utf16_names_the_charset(tmp_path, capsys, monkeypatch):
    """The Content-Type did say UTF-16: the body is broken, not unannounced."""
    body = "openapi: 3.0.0\n".encode("utf-16")[:-1]  # an odd number of bytes
    _served(monkeypatch, body, "text/yaml; charset=UTF_16")
    line = _one_line_and_two("dump-ir", tmp_path, "https://spec.example/o.yaml", capsys)
    assert "does not say so" not in line
    assert "the response is not valid UTF_16 text (byte 0x" in line


@pytest.mark.parametrize(
    "value, expected",
    [
        ("!!int SECRET-0123456789-abcdefghijklmnopqrstuvwxyz-TAIL",
         "cannot read the value 'SECRET-0123456789-abcdefghijklmnopqrstuv…': "
         "invalid literal for int() with base 10 (line 11, column 24)"),
        ("!!timestamp zzz",
         "cannot read the value 'zzz': not a value its tag can hold (line 11, column 24)"),
    ],
)
def test_a_value_its_tag_cannot_hold_is_one_line(value, expected, tmp_path, capsys):
    """The error's own text repeats the value whole; only the clipped value is shown."""
    source = _spec_file(tmp_path, "spec.yaml", _IMPOSSIBLE_DATE.replace("2023-02-29", value))
    line = _one_line_and_two("dump-ir", tmp_path, source, capsys)
    assert line.endswith(f"is not valid YAML: {expected}"), line
    assert "TAIL" not in line


@pytest.mark.parametrize("to_file", [False, True])
def test_dump_ir_of_a_lone_surrogate_is_one_line(to_file, tmp_path, capsys):
    """A "\\ud800" escape cannot be encoded into a file or onto stdout."""
    spec = FIXTURE.read_text(encoding="utf-8").replace(
        "title: Sample Shop API", 'title: "Sample \\ud800 Shop"'
    )
    source = _spec_file(tmp_path, "surrogate.yaml", spec)
    out = tmp_path / "ir.json"
    argv = ["dump-ir", source] + (["-o", str(out)] if to_file else [])
    capsys.readouterr()
    assert cli_main(argv) == 2
    captured = capsys.readouterr()
    lines = captured.err.strip().splitlines()
    assert len(lines) == 1 and "lone surrogate" in lines[0], captured.err
    assert captured.out == ""
    assert not out.exists()


def test_dump_ir_onto_a_read_only_file_leaves_no_temporary_file(tmp_path, capsys):
    """The mode copied from a read-only target made the temporary file read-only, and on
    Windows it could not be deleted after the replace failed."""
    import os
    import stat

    out = tmp_path / "ir.json"
    out.write_text("previous", encoding="utf-8")
    os.chmod(out, stat.S_IREAD)
    try:
        code = cli_main(["dump-ir", str(FIXTURE), "-o", str(out)])
        leftovers = [p.name for p in tmp_path.iterdir() if p != out]
        if os.name == "nt":
            assert code == 2, "Windows does not replace a read-only file"
            assert out.read_text(encoding="utf-8") == "previous"
        assert leftovers == [], leftovers
    finally:
        os.chmod(out, stat.S_IREAD | stat.S_IWRITE)


def test_a_bare_sync_against_the_placeholder_warns(tmp_path, capsys):
    """Without --file/--url sync reads docs/openapi.yaml; still the placeholder, it would
    rewrite paths.py without the tags the project was generated with."""
    dest = tmp_path / "proj"
    assert cli_main(["from-openapi", str(dest), "--file", str(FIXTURE)]) == 0
    from partest_gen.skeleton import _PLACEHOLDER_OPENAPI

    (dest / "docs" / "openapi.yaml").write_text(_PLACEHOLDER_OPENAPI, encoding="utf-8")
    capsys.readouterr()
    assert cli_main(["sync-openapi", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "Warning: docs/openapi.yaml is still the skeleton's /health placeholder" in out
    assert "(items)" in out

    # an explicit source, or a placeholder in a project with no other tags: no warning
    assert cli_main(["sync-openapi", str(dest), "--file", str(dest / "docs/openapi.yaml")]) == 0
    assert "Warning: docs/openapi.yaml" not in capsys.readouterr().out
    fresh = tmp_path / "fresh"
    assert cli_main(["init", str(fresh)]) == 0
    capsys.readouterr()
    assert cli_main(["sync-openapi", str(fresh)]) == 0
    assert "Warning: docs/openapi.yaml" not in capsys.readouterr().out
