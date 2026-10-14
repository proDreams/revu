"""What a single source file looks like after being parsed.

The barest structure a review needs to reason about code it cannot see: which
symbols exist, where they start and end, what they call, and what they import.
Deliberately flat data — the parsing engine (tree-sitter) stays in infrastructure,
and everything that decides *what to include* works on these values.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SymbolDTO:
    """One function, method or class of a file."""

    kind: str
    """``function``, ``method`` or ``class``."""

    name: str
    #: ``Class.method`` for a method, the plain name otherwise.
    qualified_name: str
    #: 1-based lines, inclusive.
    start_line: int
    end_line: int
    #: The declaration line(s) alone: what a caller of this symbol has to know.
    signature: str
    #: The whole symbol, signature included: what a reviewer of its body has to know.
    body: str

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass(frozen=True, slots=True)
class ImportDTO:
    """One import statement of a file."""

    #: A module path (``revu.domain.entities``) or a relative specifier (``./utils``).
    module: str
    #: Names brought into scope; empty for a bare ``import x``.
    names: tuple[str, ...] = ()
    #: Whether the specifier is relative to this file (``from .x import y``).
    relative: bool = False


@dataclass(frozen=True, slots=True)
class ParsedFileDTO:
    """A parsed source file."""

    #: The grammar that parsed it, or ``""`` when nothing could.
    language: str = ""
    symbols: tuple[SymbolDTO, ...] = ()
    imports: tuple[ImportDTO, ...] = ()
    #: Identifiers the file mentions — calls and annotations — as a set for lookups.
    referenced_names: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_parsed(self) -> bool:
        """Whether a grammar understood this file at all."""
        return bool(self.language)

    def symbols_covering(self, first_line: int, last_line: int) -> tuple[SymbolDTO, ...]:
        """The symbols whose body overlaps a line range, innermost first.

        The diff tells us which lines changed; this turns that into "which
        functions a reviewer has to see in full".
        """
        covering = [
            symbol for symbol in self.symbols if symbol.start_line <= last_line and symbol.end_line >= first_line
        ]

        # A method and its class both cover a changed line; the method is what the
        # reader needs, so the narrowest symbols come first.
        return tuple(sorted(covering, key=lambda symbol: symbol.line_count))

    def find(self, name: str) -> SymbolDTO | None:
        """The symbol called ``name``, qualified or plain."""
        for symbol in self.symbols:
            if name in (symbol.name, symbol.qualified_name):
                return symbol

        return None
