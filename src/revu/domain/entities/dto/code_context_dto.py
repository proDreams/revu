"""The surrounding code a review was given, and what it cost.

Kept as a list of titled blocks rather than one big string: the application decides
what is worth including, the prompt layer decides how it looks, and the log gets
the numbers needed to tune the budgets against real runs.
"""

from dataclasses import dataclass, field

#: Rough characters per token for source code. Only ever used to print an estimate
#: for the operator; no provider tokenizer is involved.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class ContextEntryDTO:
    """One block of surrounding code: a symbol body, a signature, a test file."""

    #: ``symbol``, ``signature``, ``tests`` or ``file``.
    kind: str
    path: str
    #: Human-readable heading, e.g. ``ReviewService._run_review (строки 60-140)``.
    title: str
    text: str

    @property
    def size(self) -> int:
        return len(self.text)


@dataclass(frozen=True, slots=True)
class ContextStatsDTO:
    """What gathering the context did, in numbers the operator can act on."""

    depth: str = "flat"
    #: Files the pull request touches.
    changed_files: int = 0
    #: Files whose *bodies* were included (subset of the changed ones).
    body_files: int = 0
    #: Additional files fetched: dependencies and tests.
    extra_files: int = 0
    symbols: int = 0
    signatures: int = 0
    tests: int = 0
    #: Files included whole because no grammar understood them.
    unparsed_files: int = 0
    chars: int = 0
    #: Whether a budget stopped the gathering.
    truncated: bool = False
    #: Requests the context cost, file reads and listings together.
    requests: int = 0
    seconds: float = 0.0
    #: Why the context is missing, when it is.
    degraded: str = ""

    @property
    def estimated_tokens(self) -> int:
        return self.chars // CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class CodeContextDTO:
    """Everything that will be shown to the model besides the diff and the comments."""

    entries: tuple[ContextEntryDTO, ...] = ()
    #: The shape of the repository: directories with a few names each. Not an entry —
    #: it is not code around the change but the ground the change stands on, and it is
    #: read by the model before it reads any of the entries.
    structure: str = ""
    stats: ContextStatsDTO = field(default_factory=ContextStatsDTO)

    @property
    def is_empty(self) -> bool:
        return not self.entries and not self.structure

    @property
    def chars(self) -> int:
        return sum(entry.size for entry in self.entries) + len(self.structure)
