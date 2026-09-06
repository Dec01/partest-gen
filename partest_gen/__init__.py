"""Scaffold a runnable pytest + partest suite from an OpenAPI specification.

Turns a specification into an intermediate representation (:mod:`partest_gen.ir`), then
emits a monorepo: endpoints, payloads, validations, collection facades and the priority-one
test stubs the methodology in ``partest.methodology`` says each operation needs. An optional
UI layer is generated alongside, deliberately isolated from the API session.

Entry points: the ``partest-gen`` command (:mod:`partest_gen.cli`) for people, and
:func:`load_openapi` + :func:`emit_resources` for scripts.

Legacy modules ``models_*`` remain for compatibility; new code uses IR + CLI.
"""

from partest_gen.emitters.resources import emit_resources
from partest_gen.ir import OpIR, ParamIR, SuiteIR, build_ir_from_openapi_dict
from partest_gen.openapi_load import load_openapi
from partest_gen.ui_layout import build_ui_files

# The one place the version lives. setup.py reads it; nothing else may repeat it.
__version__ = "1.0.0"

__all__ = [
    "OpIR",
    "ParamIR",
    "SuiteIR",
    "build_ir_from_openapi_dict",
    "load_openapi",
    "emit_resources",
    "build_ui_files",
    "__version__",
]
