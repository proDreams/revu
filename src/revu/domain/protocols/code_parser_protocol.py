"""Turning source text into symbols, imports and referenced names."""

from typing import Protocol, runtime_checkable

from revu.domain.entities.dto.parsed_file_dto import ParsedFileDTO


@runtime_checkable
class CodeParserProtocol(Protocol):
    """A source-code parser.

    One method is enough: a path decides the grammar, and a file no grammar
    understands comes back with an empty :class:`ParsedFileDTO` rather than an
    exception, because "this language is not supported" is a normal answer and not
    a failure of the review.
    """

    def supports(self, path: str) -> bool:
        """Whether a grammar is known for this path."""
        ...

    def parse(self, path: str, source: str) -> ParsedFileDTO:
        """Parse one file. Never raises for a language or syntax it cannot handle."""
        ...
