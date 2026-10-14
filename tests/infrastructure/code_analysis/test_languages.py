"""The grammar registry: which path maps to which grammar, and how loading fails."""

import pytest

from revu.infrastructure.code_analysis import languages

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("extension", "grammar"), sorted(languages.EXTENSION_TO_GRAMMAR.items()))
def test_every_supported_extension_resolves_to_its_grammar(extension: str, grammar: str) -> None:
    assert languages.grammar_for_path(f"src/pkg/module{extension}") == grammar
    # Extensions are matched case-insensitively: a repository can hold `Main.Java`.
    assert languages.grammar_for_path(f"MODULE{extension.upper()}") == grammar


@pytest.mark.parametrize(("filename", "grammar"), sorted(languages.FILENAME_TO_GRAMMAR.items()))
def test_extensionless_filenames_resolve_by_name(filename: str, grammar: str) -> None:
    assert languages.grammar_for_path(filename) == grammar
    assert languages.grammar_for_path(f"sub/dir/{filename.title()}") == grammar


def test_every_grammar_a_path_can_reach_has_extraction_tables() -> None:
    reachable = set(languages.EXTENSION_TO_GRAMMAR.values()) | set(languages.FILENAME_TO_GRAMMAR.values())

    assert reachable <= set(languages.SPECS)
    # A loader without a spec would parse into nothing, and a spec without a loader
    # would never be reachable; both are silent bugs, so the two sets are equal.
    assert set(languages.SPECS) == set(languages._GRAMMAR_SOURCES)


@pytest.mark.parametrize("path", ["notes.txt", "README", "", "src/", ".gitignore", "archive.tar", "Makefile.am"])
def test_unknown_paths_have_no_grammar(path: str) -> None:
    assert languages.grammar_for_path(path) is None


def test_windows_style_paths_are_split_on_the_backslash() -> None:
    assert languages.grammar_for_path("src\\revu\\main.py") == "python"


def test_languages_are_built_once_and_shared() -> None:
    assert languages.language_for("python") is languages.language_for("python")


def test_unknown_grammar_has_no_language() -> None:
    assert languages.language_for("no-such-grammar") is None


def test_a_missing_wheel_degrades_to_no_language(monkeypatch) -> None:
    monkeypatch.setitem(languages._GRAMMAR_SOURCES, "missing", ("revu.no_such_module", "language"))

    assert languages.language_for("missing") is None


def test_a_wheel_that_returns_something_else_degrades_to_no_language(monkeypatch) -> None:
    # `Path()` is callable with no arguments and returns a real object, just not a
    # language pointer, so `Language(...)` raises and the grammar has to disappear
    # rather than take the review down.
    monkeypatch.setitem(languages._GRAMMAR_SOURCES, "bad-pointer", ("pathlib", "Path"))

    assert languages.language_for("bad-pointer") is None


def test_grammars_exposing_a_legacy_int_pointer_still_load() -> None:
    # tree-sitter-perl and tree-sitter-dockerfile return a deprecated int pointer
    # instead of a capsule; the loader must accept both without raising.
    assert languages.language_for("perl") is not None
    assert languages.language_for("dockerfile") is not None
