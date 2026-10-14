"""The value objects that describe surrounding code and what it cost."""

import pytest

from revu.domain.entities.dto.code_context_dto import (
    CHARS_PER_TOKEN,
    CodeContextDTO,
    ContextEntryDTO,
    ContextStatsDTO,
)
from revu.domain.entities.dto.parsed_file_dto import (
    ImportDTO,
    ParsedFileDTO,
    SymbolDTO,
)

pytestmark = pytest.mark.unit


def _symbol(name: str = "run", start: int = 1, end: int = 10) -> SymbolDTO:
    return SymbolDTO(
        kind="function",
        name=name,
        qualified_name=name,
        start_line=start,
        end_line=end,
        signature=f"def {name}():",
        body=f"def {name}():\n    pass",
    )


def test_an_entry_knows_its_size():
    assert ContextEntryDTO(kind="symbol", path="a.py", title="t", text="12345").size == 5


def test_a_context_sums_its_entries_and_estimates_tokens():
    context = CodeContextDTO(
        entries=(
            ContextEntryDTO(kind="symbol", path="a.py", title="t", text="x" * 8),
            ContextEntryDTO(kind="signature", path="b.py", title="t", text="y" * 8),
        ),
        stats=ContextStatsDTO(chars=16),
    )

    assert context.is_empty is False
    assert context.chars == 16
    assert context.stats.estimated_tokens == 16 // CHARS_PER_TOKEN


def test_an_empty_context_says_so():
    assert CodeContextDTO().is_empty is True


def test_a_symbol_knows_how_long_it_is():
    assert _symbol(start=3, end=12).line_count == 10


def test_a_parsed_file_says_whether_a_grammar_read_it():
    assert ParsedFileDTO(language="python").is_parsed is True
    assert ParsedFileDTO().is_parsed is False


def test_the_symbols_covering_a_range_come_back_innermost_first():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(
            _symbol("Service", 1, 200),
            _symbol("run", 5, 20),
            _symbol("far_away", 300, 400),
        ),
    )

    covering = parsed.symbols_covering(10, 12)

    assert [symbol.name for symbol in covering] == ["run", "Service"]


def test_nothing_covers_a_line_outside_every_symbol():
    parsed = ParsedFileDTO(language="python", symbols=(_symbol("run", 50, 60),))

    assert parsed.symbols_covering(1, 5) == ()


def test_a_symbol_can_be_found_by_its_plain_or_qualified_name():
    parsed = ParsedFileDTO(
        language="python",
        symbols=(SymbolDTO("method", "save", "Repo.save", 1, 2, "def save(self):", "def save(self):\n    pass"),),
    )

    assert parsed.find("Repo.save") is not None
    assert parsed.find("save") is not None
    assert parsed.find("missing") is None


def test_an_import_remembers_its_relative_flag():
    assert ImportDTO(module=".pkg", names=("x",), relative=True).relative is True
    assert ImportDTO(module="pkg").names == ()
