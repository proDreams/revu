"""Gathering surrounding code: what is picked, and what is left out."""

from unittest.mock import AsyncMock

import pytest

from revu.application.entities.enums.context_depth_enums import ContextDepthEnum
from revu.application.services.context_builder import (
    ContextBuilder,
    ContextRequest,
    changed_files,
    resolve_module,
    skipped_path,
)
from revu.application.services.context_builder import test_candidates as find_test_candidates
from revu.domain.entities.dto.parsed_file_dto import (
    ImportDTO,
    ParsedFileDTO,
    SymbolDTO,
)

pytestmark = pytest.mark.unit

DIFF = """diff --git a/src/app/service.py b/src/app/service.py
--- a/src/app/service.py
+++ b/src/app/service.py
@@ -1,3 +1,4 @@
 import os
-from typing import Any
+from typing import Any, Final
+import sys
 context
"""

REPO = "owner/repo"
REVISION = "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"


def _diff_for(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1,2 @@
 context
+added
"""


def symbol(
    name: str,
    start: int,
    end: int,
    *,
    kind: str = "function",
    qualified: str | None = None,
) -> SymbolDTO:
    return SymbolDTO(
        kind=kind,
        name=name,
        qualified_name=qualified or name,
        start_line=start,
        end_line=end,
        signature=f"def {name}(...):",
        body=f"def {name}(...):\n    body of {name}",
    )


class FakeParser:
    """A parser with canned answers, so the builder can be tested on its own."""

    def __init__(self, files: dict[str, ParsedFileDTO]) -> None:
        self.files = files

    def supports(self, path: str) -> bool:
        return path in self.files

    def parse(self, path: str, source: str) -> ParsedFileDTO:
        return self.files.get(path, ParsedFileDTO())


def context_of(
    parser: FakeParser,
    contents: dict[str, str],
    *,
    depth: ContextDepthEnum = ContextDepthEnum.DEEP,
    files: int = 12,
    chars: int = 40_000,
    tree: tuple[str, ...] = (),
    diff: str = DIFF,
) -> tuple[AsyncMock, ContextRequest]:
    port = AsyncMock()
    port.list_files.return_value = tree or tuple(contents)
    port.fetch_file.side_effect = lambda repo, path, revision: contents.get(path)

    request = ContextRequest(
        repo=REPO,
        revision=REVISION,
        diff=diff,
        depth=depth,
        max_extra_files=files,
        max_chars=chars,
    )

    return port, request


async def build(parser: FakeParser, **kwargs):
    port, request = context_of(parser, **kwargs)
    context = await ContextBuilder(parser=parser).build(port, request)

    return port, context


# ── the diff decides what is looked at ──────────────────────────────────────


def test_the_diff_says_which_files_and_lines_changed():
    changed = changed_files(DIFF)

    assert [file.path for file in changed] == ["src/app/service.py"]
    assert changed[0].changes == 3  # one removal, two additions
    # Lines 1-4 of the new revision are the hunk, so that is one range.
    assert changed[0].ranges == ((1, 4),)


def test_a_deletion_still_reports_where_it_happened():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,2 +10,1 @@
 context
-gone
"""

    assert changed_files(diff)[0].ranges == ((10, 10),)


# ── the three kinds of context ─────────────────────────────────────────────


async def test_flat_depth_reads_nothing_at_all():
    parser = FakeParser({"src/app/service.py": ParsedFileDTO(language="python")})

    port, context = await build(parser, contents={}, depth=ContextDepthEnum.FLAT)

    assert context.entries == ()
    assert context.stats.depth == ContextDepthEnum.FLAT
    assert context.stats.changed_files == 1
    assert port.list_files.await_count == 0
    assert port.fetch_file.await_count == 0


async def test_the_changed_symbol_is_included_in_full():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    parser = FakeParser({"src/app/service.py": parsed})

    port, context = await build(parser, contents={"src/app/service.py": "def run(): pass"})

    entry = context.entries[0]
    assert (entry.kind, entry.path) == ("symbol", "src/app/service.py")
    assert entry.text == "def run(...):\n    body of run"
    assert "строки 1-20" in entry.title
    assert context.stats.symbols == 1
    assert context.stats.body_files == 1
    assert port.list_files.await_count == 1


async def test_the_innermost_symbol_wins():
    """A changed line inside a method must not drag the whole class in."""
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("Service", 1, 200, kind="class"), symbol("run", 1, 20, kind="method", qualified="Service.run")),
    )
    parser = FakeParser({"src/app/service.py": parsed})

    _, context = await build(parser, contents={"src/app/service.py": "class Service: pass"})

    assert [entry.title.split(" ")[0] for entry in context.entries] == ["Service.run"]


async def test_an_imported_name_that_is_used_contributes_its_signature():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Repo",)),),
        referenced_names=frozenset({"Repo"}),
    )
    dependency = ParsedFileDTO(language="python", symbols=(symbol("Repo", 1, 40, kind="class"),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/repo.py": dependency})

    _, context = await build(
        parser,
        contents={"src/app/service.py": "def run(): pass", "src/app/repo.py": "class Repo: pass"},
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    kinds = [entry.kind for entry in context.entries]
    assert kinds == ["symbol", "signature"]
    assert context.entries[1].path == "src/app/repo.py"
    assert context.entries[1].text == "def Repo(...):"
    assert context.stats.extra_files == 1


async def test_an_imported_name_that_is_never_used_is_left_out():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Unused",)),),
        referenced_names=frozenset({"other"}),
    )
    dependency = ParsedFileDTO(language="python", symbols=(symbol("Unused", 1, 5),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/repo.py": dependency})

    port, context = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/repo.py": "y"},
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert port.fetch_file.await_count == 2


async def test_an_imported_module_that_is_not_in_the_tree_is_skipped():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="missing.module", names=("Thing",)),),
        referenced_names=frozenset({"Thing"}),
    )
    parser = FakeParser({"src/app/service.py": parsed})

    _, context = await build(parser, contents={"src/app/service.py": "x"}, tree=("src/app/service.py",))

    assert [entry.kind for entry in context.entries] == ["symbol"]


async def test_the_test_file_next_to_the_code_is_included():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    tests = ParsedFileDTO(language="python", symbols=(symbol("test_run", 1, 3), symbol("test_other", 5, 7)))
    parser = FakeParser({"src/app/service.py": parsed, "tests/app/test_service.py": tests})

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "tests/app/test_service.py": "y"},
        tree=("src/app/service.py", "tests/app/test_service.py"),
    )

    tests_entry = context.entries[-1]
    assert tests_entry.kind == "tests"
    assert "тесты: 2" in tests_entry.title
    assert context.stats.tests == 2


async def test_only_one_test_file_is_taken_per_changed_file():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    tests = ParsedFileDTO(language="python", symbols=(symbol("test_run", 1, 3),))
    parser = FakeParser(
        {
            "src/app/service.py": parsed,
            "tests/a/test_service.py": tests,
            "tests/b/service_test.py": tests,
        }
    )

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "tests/a/test_service.py": "y", "tests/b/service_test.py": "z"},
        tree=("src/app/service.py", "tests/a/test_service.py", "tests/b/service_test.py"),
    )

    assert len([entry for entry in context.entries if entry.kind == "tests"]) == 1


# ── languages, budgets, failures ───────────────────────────────────────────


async def test_a_language_without_a_grammar_falls_back_to_the_whole_file():
    """Precision needs a grammar; having context at all must not depend on one."""
    parser = FakeParser({})  # knows nothing, so the file comes back unparsed
    contents = {"src/app/service.py": "some text no grammar understood"}

    _, context = await build(parser, contents=contents)

    entry = context.entries[0]
    assert entry.kind == "file"
    assert entry.text == contents["src/app/service.py"]
    assert context.stats.unparsed_files == 1


async def test_the_character_budget_stops_the_gathering():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    parser = FakeParser({"src/app/service.py": parsed})

    _, context = await build(parser, contents={"src/app/service.py": "x"}, chars=1)

    assert context.entries == ()
    assert context.stats.truncated is True


async def test_the_extra_file_budget_stops_the_dependencies():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Repo",)),),
        referenced_names=frozenset({"Repo"}),
    )
    dependency = ParsedFileDTO(language="python", symbols=(symbol("Repo", 1, 40),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/repo.py": dependency})

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/repo.py": "y"},
        files=0,
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert context.stats.truncated is True


async def test_a_secret_or_generated_path_is_never_read():
    diff = """diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -1,1 +1,1 @@
-OLD=1
+NEW=2
"""
    parser = FakeParser({})

    port, context = await build(parser, contents={".env": "NEW=2"}, diff=diff)

    assert context.entries == ()
    assert port.fetch_file.await_count == 0


async def test_a_file_that_is_not_in_the_tree_is_skipped():
    parser = FakeParser({"src/app/service.py": ParsedFileDTO(language="python")})

    _, context = await build(parser, contents={})

    assert context.entries == ()
    assert context.stats.body_files == 0


async def test_a_failing_host_degrades_instead_of_failing_the_review(caplog):
    parser = FakeParser({})
    port = AsyncMock()
    port.list_files.side_effect = RuntimeError("503 Service Unavailable")
    request = ContextRequest(
        repo=REPO,
        revision=REVISION,
        diff=DIFF,
        depth=ContextDepthEnum.DEEP,
        max_extra_files=12,
        max_chars=40_000,
    )

    with caplog.at_level("WARNING"):
        context = await ContextBuilder(parser=parser).build(port, request)

    assert context.entries == ()
    assert "503 Service Unavailable" in context.stats.degraded
    assert "reviewing from the diff" in caplog.text


async def test_a_file_is_read_only_once_even_when_it_is_also_a_dependency():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.service_helper", names=("Thing",)),),
        referenced_names=frozenset({"Thing"}),
    )
    helper = ParsedFileDTO(language="python", symbols=(symbol("Thing", 1, 3),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/service_helper.py": helper})

    port, _ = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/service_helper.py": "y"},
        tree=("src/app/service.py", "src/app/service_helper.py"),
    )

    # One listing, then one read per distinct file.
    assert port.fetch_file.await_count == 2


# ── path helpers ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [".env", "app/.env.local", "config/secrets.yaml", "app/credentials.json", "node_modules/x/y.js", "id_rsa"],
)
def test_secrets_and_generated_noise_are_never_sent(path):
    assert skipped_path(path) is True


@pytest.mark.parametrize("path", ["src/app/service.py", "tests/test_service.py", "web/utils.ts", "Makefile"])
def test_ordinary_sources_are_allowed(path):
    assert skipped_path(path) is False


TREE = (
    "src/revu/app/service.py",
    "src/revu/app/__init__.py",
    "src/revu/domain/entities/dto.py",
    "web/utils.ts",
    "web/deep/thing.ts",
    "tests/app/test_service.py",
)


@pytest.mark.parametrize(
    ("path", "imported", "expected"),
    [
        ("src/revu/app/service.py", ImportDTO("revu.domain.entities.dto", ("X",)), "src/revu/domain/entities/dto.py"),
        ("src/revu/app/service.py", ImportDTO(".dto", ("X",), relative=True), "src/revu/domain/entities/dto.py"),
        (
            "src/revu/app/service.py",
            ImportDTO("..domain.entities.dto", ("X",), relative=True),
            "src/revu/domain/entities/dto.py",
        ),
        ("web/app.ts", ImportDTO("./utils", ("x",), relative=True), "web/utils.ts"),
        ("web/deep/app.ts", ImportDTO("../utils", ("x",), relative=True), "web/utils.ts"),
        ("web/app.ts", ImportDTO("./nothing", ("x",), relative=True), None),
    ],
)
def test_a_module_specifier_resolves_to_a_path(path, imported, expected):
    assert resolve_module(path, imported, TREE) == expected


def test_a_test_file_is_found_by_the_name_of_what_it_covers():
    assert find_test_candidates("src/revu/app/service.py", TREE) == ("tests/app/test_service.py",)
    assert find_test_candidates("web/utils.ts", ("web/utils.test.ts",)) == ("web/utils.test.ts",)
    assert find_test_candidates("src/app/other.py", TREE) == ()


async def test_a_file_already_read_is_taken_from_the_cache():
    """Two changed files may import the same module; it is read once, added once."""
    helper = ParsedFileDTO(language="python", symbols=(symbol("Thing", 1, 3),))
    first = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20, qualified="First.run"),),
        imports=(ImportDTO(module="src.app.helper", names=("Thing",)),),
        referenced_names=frozenset({"Thing"}),
    )
    second = ParsedFileDTO(
        language="python",
        symbols=(symbol("other", 1, 20, qualified="Second.other"),),
        imports=(ImportDTO(module="src.app.helper", names=("Thing",)),),
        referenced_names=frozenset({"Thing"}),
    )
    parser = FakeParser({"src/app/service.py": first, "src/app/other.py": second, "src/app/helper.py": helper})
    diff = """diff --git a/src/app/service.py b/src/app/service.py
--- a/src/app/service.py
+++ b/src/app/service.py
@@ -1,2 +1,3 @@
 context
+added
 context2
diff --git a/src/app/other.py b/src/app/other.py
--- a/src/app/other.py
+++ b/src/app/other.py
@@ -1,2 +1,3 @@
 context
+added
 context2
"""
    contents = {"src/app/service.py": "x", "src/app/other.py": "y", "src/app/helper.py": "z"}
    tree = ("src/app/service.py", "src/app/other.py", "src/app/helper.py")

    port, request = context_of(parser, contents, tree=tree, diff=diff)
    context = await ContextBuilder(parser=parser).build(port, request)

    # One listing, then one read per distinct file: the helper is not read twice.
    assert port.fetch_file.await_count == 3
    kinds = [entry.kind for entry in context.entries]
    assert kinds.count("symbol") == 2
    # Reached from both files, but added to the prompt once.
    assert kinds.count("signature") == 1


async def test_a_symbol_that_does_not_fit_the_budget_is_left_out():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    parser = FakeParser({"src/app/service.py": parsed})
    body_size = len(parsed.symbols[0].body)

    _, context = await build(parser, contents={"src/app/service.py": "x"}, chars=body_size - 1)

    assert context.entries == ()
    assert context.stats.truncated is True


async def test_a_signature_that_does_not_fit_the_budget_is_left_out():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Repo",)),),
        referenced_names=frozenset({"Repo"}),
    )
    dependency = ParsedFileDTO(language="python", symbols=(symbol("Repo", 1, 40),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/repo.py": dependency})
    body_size = len(parsed.symbols[0].body)

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/repo.py": "y"},
        chars=body_size + len(dependency.symbols[0].signature) - 1,
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert context.stats.truncated is True


async def test_a_test_file_that_does_not_fit_the_budget_is_left_out():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    tests = ParsedFileDTO(language="python", symbols=(symbol("test_run", 1, 3),))
    parser = FakeParser({"src/app/service.py": parsed, "tests/app/test_service.py": tests})
    body_size = len(parsed.symbols[0].body)

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "tests/app/test_service.py": "y"},
        chars=body_size + 1,
        tree=("src/app/service.py", "tests/app/test_service.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert context.stats.truncated is True


async def test_a_dependency_the_parser_cannot_read_contributes_nothing():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Repo",)),),
        referenced_names=frozenset({"Repo"}),
    )
    parser = FakeParser({"src/app/service.py": parsed})  # the dependency is unknown

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/repo.py": "y"},
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]


async def test_a_dependency_on_a_skipped_path_is_not_read():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="config.secrets", names=("Key",)),),
        referenced_names=frozenset({"Key"}),
    )
    parser = FakeParser({"src/app/service.py": parsed})

    port, context = await build(
        parser,
        contents={"src/app/service.py": "x", "config/secrets.py": "TOKEN=1"},
        tree=("src/app/service.py", "config/secrets.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert port.fetch_file.await_count == 1


def test_lines_that_are_not_next_to_each_other_become_separate_ranges():
    from revu.application.services.context_builder import _ranges

    assert _ranges([]) == ()
    assert _ranges([1, 2, 3, 10]) == ((1, 3), (10, 10))
    assert _ranges([5, 5, 5]) == ((5, 5),)


async def test_a_parsed_file_without_a_covering_symbol_is_shown_whole():
    """A changed import in a Python file sits in no function, so nothing narrower fits."""
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 50, 60),))
    parser = FakeParser({"src/app/service.py": parsed})
    contents = {"src/app/service.py": "import os\n"}

    _, context = await build(parser, contents=contents)

    entry = context.entries[0]
    assert entry.kind == "file"
    assert "символы не найдены" in entry.title
    assert entry.text == contents["src/app/service.py"]
    # It was understood by a grammar, so it is not an unparsed language.
    assert context.stats.unparsed_files == 0
    assert context.stats.body_files == 1


async def test_a_config_file_without_symbols_is_shown_whole():
    parser = FakeParser({"src/app/config.yaml": ParsedFileDTO(language="yaml")})
    contents = {"src/app/config.yaml": "key: value\n"}

    _, context = await build(parser, contents=contents, diff=_diff_for("src/app/config.yaml"))

    assert context.entries[0].text == "key: value\n"


async def test_an_imported_name_the_dependency_does_not_define_is_skipped():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(symbol("run", 1, 20),),
        imports=(ImportDTO(module="src.app.repo", names=("Missing",)),),
        referenced_names=frozenset({"Missing"}),
    )
    dependency = ParsedFileDTO(language="python", symbols=(symbol("Other", 1, 5),))
    parser = FakeParser({"src/app/service.py": parsed, "src/app/repo.py": dependency})

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "src/app/repo.py": "y"},
        tree=("src/app/service.py", "src/app/repo.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]


async def test_a_test_file_the_parser_cannot_read_is_skipped():
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    parser = FakeParser({"src/app/service.py": parsed, "tests/app/test_service.py": ParsedFileDTO(language="python")})

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "tests/app/test_service.py": "y"},
        tree=("src/app/service.py", "tests/app/test_service.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert context.stats.tests == 0


async def test_a_whole_file_that_does_not_fit_the_budget_is_left_out():
    parser = FakeParser({})  # nothing parses, so the file would be shown whole
    contents = {"src/app/service.py": "x" * 500}

    _, context = await build(parser, contents=contents, chars=100)

    assert context.entries == ()
    assert context.stats.truncated is True


def test_a_hunk_that_only_removes_lines_still_reports_where():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,1 +10,0 @@
-gone
"""

    assert changed_files(diff)[0].ranges == ((10, 10),)


def test_a_relative_import_that_resolves_to_nothing_is_left_alone():
    assert resolve_module("app.py", ImportDTO(module=".", relative=True), ("app.py",)) is None


async def test_the_test_lookup_stops_when_the_budget_is_gone():
    """Reaching the test file is the last step, and the first thing to be cut."""
    parsed = ParsedFileDTO(language="python", symbols=(symbol("run", 1, 20),))
    tests = ParsedFileDTO(language="python", symbols=(symbol("test_run", 1, 3),))
    parser = FakeParser({"src/app/service.py": parsed, "tests/app/test_service.py": tests})
    body_size = len(parsed.symbols[0].body)

    _, context = await build(
        parser,
        contents={"src/app/service.py": "x", "tests/app/test_service.py": "y"},
        chars=body_size,
        tree=("src/app/service.py", "tests/app/test_service.py"),
    )

    assert [entry.kind for entry in context.entries] == ["symbol"]
    assert context.stats.truncated is True
