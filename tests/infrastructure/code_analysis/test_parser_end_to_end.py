"""The parser as the context builder uses it: real grammars, real source."""

import pytest

from revu.domain.protocols.code_parser_protocol import CodeParserProtocol
from revu.infrastructure.code_analysis.tree_sitter_parser import TreeSitterCodeParser

pytestmark = pytest.mark.unit

PYTHON_SOURCE = '''import os
from typing import Any, Final
from .helpers import Thing


class Service:
    """A service."""

    def run(self, item: Any) -> Final:
        other = Thing()
        return self._handle(other)


def standalone(value: Any) -> str:
    return str(value)
'''

TYPESCRIPT_SOURCE = """import { helper } from './helper';

export class Service {
  run(item: number): number {
    return helper(item);
  }
}
"""

GO_SOURCE = """package main

type Repo struct{}

func (r Repo) Save(item int) int {
	return item
}

func main() {
	r := Repo{}
	r.Save(1)
}
"""


@pytest.fixture
def parser() -> TreeSitterCodeParser:
    return TreeSitterCodeParser()


def test_the_parser_implements_the_protocol(parser):
    assert isinstance(parser, CodeParserProtocol)


def test_a_python_file_yields_its_symbols_with_lines(parser):
    parsed = parser.parse("service.py", PYTHON_SOURCE)

    assert parsed.language == "python"
    assert parsed.is_parsed is True
    names = [symbol.qualified_name for symbol in parsed.symbols]
    assert "Service" in names
    assert "Service.run" in names
    assert "standalone" in names

    run = parsed.find("Service.run")
    assert run is not None
    assert run.kind == "method"
    assert run.start_line <= run.end_line
    assert PYTHON_SOURCE.splitlines()[run.start_line - 1].strip().startswith("def run")


def test_a_python_symbol_carries_its_signature_and_its_body(parser):
    parsed = parser.parse("service.py", PYTHON_SOURCE)
    run = parsed.find("Service.run")

    assert run is not None
    assert "def run" in run.signature
    # The signature stays a header: the body is a separate field.
    assert "return" not in run.signature
    assert "return" in run.body


def test_python_imports_are_reported_with_their_names(parser):
    parsed = parser.parse("service.py", PYTHON_SOURCE)
    modules = {item.module for item in parsed.imports}

    assert "os" in modules
    assert "typing" in modules
    typing_import = next(item for item in parsed.imports if item.module == "typing")
    assert typing_import.names == ("Any", "Final")


def test_a_relative_python_import_is_marked_relative(parser):
    parsed = parser.parse("service.py", PYTHON_SOURCE)
    relative = [item for item in parsed.imports if item.relative]

    assert relative, "the `from .helpers import Thing` import must be relative"
    assert relative[0].module.endswith("helpers")


def test_the_referenced_names_include_what_the_code_calls(parser):
    parsed = parser.parse("service.py", PYTHON_SOURCE)

    assert "Thing" in parsed.referenced_names
    assert "_handle" in parsed.referenced_names


def test_a_typescript_file_yields_its_class_and_its_import(parser):
    parsed = parser.parse("service.ts", TYPESCRIPT_SOURCE)

    assert parsed.language == "typescript"
    assert "Service" in [symbol.qualified_name for symbol in parsed.symbols]
    assert any(item.module == "./helper" for item in parsed.imports)


def test_a_tsx_file_uses_its_own_grammar(parser):
    parsed = parser.parse("view.tsx", "export const View = () => <div>hi</div>;")

    assert parsed.language == "tsx"


def test_a_go_file_yields_its_functions_and_methods(parser):
    parsed = parser.parse("main.go", GO_SOURCE)

    assert parsed.language == "go"
    names = [symbol.qualified_name for symbol in parsed.symbols]
    assert "main" in names
    assert any(name.endswith("Save") for name in names)


@pytest.mark.parametrize(
    "path",
    ["a.py", "a.js", "a.ts", "a.tsx", "a.go", "a.java", "a.rb", "a.rs", "a.cs", "a.php", "a.sh", "a.sql", "a.yaml"],
)
def test_the_shipped_grammars_cover_the_main_languages(parser, path):
    assert parser.supports(path) is True


@pytest.mark.parametrize("path", ["notes.txt", "archive.tar.gz", ""])
def test_an_unknown_extension_is_not_supported(parser, path):
    assert parser.supports(path) is False


def test_an_unknown_extension_parses_to_an_empty_answer(parser):
    parsed = parser.parse("notes.txt", "just text")

    assert parsed.is_parsed is False
    assert parsed.symbols == ()
    assert parsed.imports == ()


@pytest.mark.parametrize("source", ["", "   \n\t\n", "def broken(:\n  ???", "\x00\x01binary-ish"])
def test_broken_or_empty_source_never_raises(parser, source):
    assert isinstance(parser.parse("a.py", source).symbols, tuple)


def test_two_languages_can_be_parsed_one_after_another(parser):
    """Every call builds its own parser, so nothing leaks between languages."""
    assert parser.parse("a.py", "def f(): pass").language == "python"
    assert parser.parse("a.go", "package main").language == "go"
    assert parser.parse("a.py", "x = 1").language == "python"


def test_a_deeply_nested_file_is_not_lost(parser):
    """A tree is as deep as the source is nested, and the walk must not care.

    Nine hundred nested calls used to exhaust the interpreter's stack; the
    `RecursionError` was swallowed by `parse`, so the file came back as one with
    nothing in it — a deep file silently left out of the review context.
    """
    text = "def f():\n    return " + "g(" * 900 + ")" * 900 + "\n"

    parsed = parser.parse("deep.py", text)

    assert [symbol.name for symbol in parsed.symbols] == ["f"]
    assert parsed.is_parsed is True


def test_a_decorator_with_nothing_to_decorate_holds_no_symbol(parser):
    """A file caught mid-write, which is a normal thing to find in a repository.

    `@dec` on its own parses — the grammars recover rather than fail — and the
    wrapper has no definition to widen, so the walk has to cope with that.
    """
    parsed = parser.parse("x.py", "@dec\n")

    assert parsed.symbols == ()
    assert parsed.is_parsed is True
