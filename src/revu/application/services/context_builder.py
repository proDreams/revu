"""Deciding what surrounding code a review gets to see.

The diff alone hides three things a reviewer needs: the rest of the symbol that was
changed, the contract of what that code calls, and whether a test covers it. This
builder fetches exactly those, in that order of importance, and stops when the
configured budget runs out.

Two rules shape everything here:

* **The diff is never trimmed.** A review that cannot see part of the change is
  worse than a review without extra context, so budgets apply to *additional* files
  and to the total size of what is added — never to the change itself.
* **Context is a bonus, never a precondition.** Any failure — a refused request, a
  language no grammar understands, an exhausted budget — costs entries and a line in
  the log, and the review continues from the diff.
"""

import time
from dataclasses import dataclass, field

from unidiff import PatchSet

from revu.application.config import get_logger
from revu.application.entities.enums.context_depth_enums import ContextDepthEnum
from revu.domain.entities.dto.code_context_dto import (
    CodeContextDTO,
    ContextEntryDTO,
    ContextStatsDTO,
)
from revu.domain.entities.dto.parsed_file_dto import ImportDTO, ParsedFileDTO, SymbolDTO
from revu.domain.protocols.code_parser_protocol import CodeParserProtocol
from revu.domain.protocols.git_reader_protocol import GitReaderProtocol
from revu.infrastructure.git_providers.repository_files import too_large

logger = get_logger(name=__name__)

#: Paths that must never reach an AI provider: secrets, and generated noise that
#: only wastes the budget.
SKIPPED_DIRECTORIES = (
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".git/",
)
SKIPPED_SUFFIXES = (".min.js", ".min.css", ".map", ".lock", ".snap")
SKIPPED_NAMES = (".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".git-credentials")
SKIPPED_NAME_PARTS = ("secret", "credential", "password", "private_key")

#: Extensions a module specifier may resolve to, in the order they are tried.
MODULE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".php", ".java")

#: How a test file is recognised from the name of the file it covers.
TEST_PATTERNS = (
    "test_{stem}{suffix}",
    "{stem}_test{suffix}",
    "{stem}.test{suffix}",
    "{stem}.spec{suffix}",
    "{stem}Test{suffix}",
    "{stem}Tests{suffix}",
    "{stem}Tests{suffix}",
    "{stem}IT{suffix}",
    "{stem}Spec{suffix}",
)

#: One symbol per changed range, and the innermost one: a changed line inside a method
#: must not drag the whole surrounding class into the prompt.
MAX_SYMBOLS_PER_RANGE = 1


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """One file of the diff, with the lines of the new revision to look at."""

    path: str
    ranges: tuple[tuple[int, int], ...]
    changes: int


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Everything the builder needs to know about one review."""

    repo: str
    revision: str
    diff: str
    depth: ContextDepthEnum
    max_extra_files: int
    max_chars: int


@dataclass(frozen=True, slots=True)
class _FileSource:
    """A file that was read: its text, and what the parser made of it."""

    content: str
    parsed: ParsedFileDTO


@dataclass
class _Budget:
    """What is left of the two budgets, and whether anything had to be cut."""

    chars_left: int
    extra_files_left: int
    truncated: bool = False

    def spend(self, entry: ContextEntryDTO, *, extra_file: bool = False) -> None:
        self.chars_left -= entry.size

        if extra_file:
            self.extra_files_left -= 1

    def cut(self) -> None:
        self.truncated = True


@dataclass
class _Gathering:
    """Mutable totals while the context is assembled."""

    entries: list[ContextEntryDTO] = field(default_factory=list)
    #: What was already added: the same symbol may be reached from several files.
    seen: set[tuple[str, str, str]] = field(default_factory=set)
    requests: int = 0
    symbols: int = 0
    signatures: int = 0
    tests: int = 0
    body_files: int = 0
    extra_files: int = 0
    unparsed_files: int = 0
    cache: dict[str, _FileSource | None] = field(default_factory=dict)


class ContextBuilder:
    """Gathers the bodies, signatures and tests that belong to a diff."""

    def __init__(self, parser: CodeParserProtocol) -> None:
        self._parser = parser

    @staticmethod
    def _add(gathering: _Gathering, entry: ContextEntryDTO) -> bool:
        """Record an entry unless the very same block is already there."""
        key = (entry.kind, entry.path, entry.title)

        if key in gathering.seen:
            return False

        gathering.seen.add(key)
        gathering.entries.append(entry)

        return True

    async def build(self, port: GitReaderProtocol, request: ContextRequest) -> CodeContextDTO:
        """The context for one review, or an empty one with a reason in the stats."""
        started = time.monotonic()
        changed = changed_files(request.diff)

        if request.depth is not ContextDepthEnum.DEEP:
            return CodeContextDTO(
                stats=ContextStatsDTO(
                    depth=request.depth,
                    changed_files=len(changed),
                    seconds=time.monotonic() - started,
                )
            )

        budget = _Budget(chars_left=request.max_chars, extra_files_left=request.max_extra_files)
        gathering = _Gathering()
        degraded = ""

        try:
            known_paths = await self._list_files(port, request, gathering)
            await self._collect(port, request, changed, known_paths, budget, gathering)
        except Exception as exc:  # noqa: BLE001 - context must never fail a review
            degraded = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "could not gather deep context for %s at %s: %s; reviewing from the diff alone",
                request.repo,
                request.revision[:8],
                degraded,
            )

        return CodeContextDTO(
            entries=tuple(gathering.entries),
            stats=ContextStatsDTO(
                depth=request.depth,
                changed_files=len(changed),
                body_files=gathering.body_files,
                extra_files=gathering.extra_files,
                symbols=gathering.symbols,
                signatures=gathering.signatures,
                tests=gathering.tests,
                unparsed_files=gathering.unparsed_files,
                chars=sum(entry.size for entry in gathering.entries),
                truncated=budget.truncated,
                requests=gathering.requests,
                seconds=time.monotonic() - started,
                degraded=degraded,
            ),
        )

    async def _list_files(
        self,
        port: GitReaderProtocol,
        request: ContextRequest,
        gathering: _Gathering,
    ) -> tuple[str, ...]:
        """The tree, once: it is what makes "which test covers this file" answerable."""
        gathering.requests += 1

        return await port.list_files(repo=request.repo, revision=request.revision)

    async def _collect(
        self,
        port: GitReaderProtocol,
        request: ContextRequest,
        changed: tuple[ChangedFile, ...],
        known_paths: tuple[str, ...],
        budget: _Budget,
        gathering: _Gathering,
    ) -> None:
        # The files with most changes first: when the budget runs out it runs out on
        # the least significant part of the pull request, not on the largest file.
        for file in sorted(changed, key=lambda item: item.changes, reverse=True):
            if skipped_path(file.path):
                continue

            source = await self._read(port, request, file.path, gathering)

            if source is None:
                continue

            covered = self._symbols_covering(source.parsed, file)

            if covered:
                self._add_symbols(covered, file, budget, gathering)
            else:
                # Either no grammar understood the file or nothing defines the changed
                # lines (a config, a Dockerfile, top-level statements). The whole file
                # is then the only context there is — if it fits the budget. A symbol
                # that merely did not fit is not replaced by the file around it: the
                # file is strictly larger, so it cannot fit either.
                self._add_whole_file(source, file, budget, gathering, parsed=source.parsed.is_parsed)

            await self._add_dependencies(port, request, file, source.parsed, known_paths, budget, gathering)
            await self._add_tests(port, request, file, known_paths, budget, gathering)

    async def _read(
        self,
        port: GitReaderProtocol,
        request: ContextRequest,
        path: str,
        gathering: _Gathering,
    ) -> _FileSource | None:
        """Fetch and parse one file, at most once per review."""
        if path in gathering.cache:
            return gathering.cache[path]

        gathering.requests += 1
        content = await port.fetch_file(repo=request.repo, path=path, revision=request.revision)

        source: _FileSource | None = None

        if content is not None and not too_large(content):
            source = _FileSource(content=content, parsed=self._parser.parse(path, content))

        gathering.cache[path] = source

        return source

    @staticmethod
    def _symbols_covering(parsed: ParsedFileDTO, file: ChangedFile) -> tuple[SymbolDTO, ...]:
        """The innermost symbol of every changed range of one file."""
        chosen: dict[str, SymbolDTO] = {}

        for first_line, last_line in file.ranges:
            for symbol in parsed.symbols_covering(first_line, last_line)[:MAX_SYMBOLS_PER_RANGE]:
                chosen.setdefault(symbol.qualified_name, symbol)

        return tuple(chosen.values())

    def _add_symbols(
        self,
        symbols: tuple[SymbolDTO, ...],
        file: ChangedFile,
        budget: _Budget,
        gathering: _Gathering,
    ) -> None:
        """A: the full body of every symbol the changed lines fall into."""
        added_bodies = 0

        for symbol in symbols:
            entry = ContextEntryDTO(
                kind="symbol",
                path=file.path,
                title=f"{symbol.qualified_name} (строки {symbol.start_line}-{symbol.end_line})",
                text=symbol.body,
            )

            if entry.size > budget.chars_left:
                budget.cut()

                continue

            budget.spend(entry)
            self._add(gathering, entry)
            gathering.symbols += 1
            added_bodies += 1

        if added_bodies:
            gathering.body_files += 1

    def _add_whole_file(
        self,
        source: _FileSource,
        file: ChangedFile,
        budget: _Budget,
        gathering: _Gathering,
        *,
        parsed: bool,
    ) -> None:
        """Show the file whole when nothing narrower could be picked.

        Precision is what a grammar buys; *having context at all* must not depend on
        one. The same applies to a file whose grammar found no symbol around the
        changed lines — a config, a Dockerfile, top-level code.
        """
        reason = "символы не найдены" if parsed else "язык не распознан"

        entry = ContextEntryDTO(
            kind="file",
            path=file.path,
            title=f"{file.path} (файл целиком: {reason})",
            text=source.content,
        )

        if entry.size > budget.chars_left:
            budget.cut()

            return

        budget.spend(entry)
        self._add(gathering, entry)
        gathering.unparsed_files += 0 if parsed else 1
        gathering.body_files += 1 if parsed else 0

    async def _add_dependencies(
        self,
        port: GitReaderProtocol,
        request: ContextRequest,
        file: ChangedFile,
        parsed: ParsedFileDTO,
        known_paths: tuple[str, ...],
        budget: _Budget,
        gathering: _Gathering,
    ) -> None:
        """B: signatures of the imported symbols the changed file actually mentions."""
        for imported in parsed.imports:
            if budget.extra_files_left <= 0 or budget.chars_left <= 0:
                budget.cut()

                return

            target = resolve_module(file.path, imported, known_paths)

            if target is None or target == file.path or skipped_path(target):
                continue

            dependency = await self._read(port, request, target, gathering)

            if dependency is None or not dependency.parsed.is_parsed:
                continue

            self._add_signatures(dependency.parsed, target, imported, parsed, budget, gathering)

    def _add_signatures(
        self,
        dependency: ParsedFileDTO,
        target: str,
        imported: ImportDTO,
        parsed: ParsedFileDTO,
        budget: _Budget,
        gathering: _Gathering,
    ) -> None:
        added = 0

        for name in imported.names:
            if name not in parsed.referenced_names:
                continue

            symbol = dependency.find(name)

            if symbol is None:
                continue

            entry = ContextEntryDTO(
                kind="signature",
                path=target,
                title=f"{symbol.qualified_name} (сигнатура, строки {symbol.start_line}-{symbol.end_line})",
                text=symbol.signature,
            )

            if entry.size > budget.chars_left:
                budget.cut()

                continue

            budget.spend(entry)
            self._add(gathering, entry)
            gathering.signatures += 1
            added += 1

        if added:
            budget.extra_files_left -= 1
            gathering.extra_files += 1

    async def _add_tests(
        self,
        port: GitReaderProtocol,
        request: ContextRequest,
        file: ChangedFile,
        known_paths: tuple[str, ...],
        budget: _Budget,
        gathering: _Gathering,
    ) -> None:
        """D: the tests that cover the changed file, by path and name."""
        for candidate in test_candidates(file.path, known_paths):
            if budget.extra_files_left <= 0 or budget.chars_left <= 0:
                budget.cut()

                return

            tests = await self._read(port, request, candidate, gathering)

            if tests is None or not tests.parsed.symbols:
                continue

            entry = ContextEntryDTO(
                kind="tests",
                path=candidate,
                title=f"{candidate} (тесты: {len(tests.parsed.symbols)})",
                text="\n".join(symbol.signature for symbol in tests.parsed.symbols),
            )

            if entry.size > budget.chars_left:
                budget.cut()

                continue

            budget.spend(entry, extra_file=True)
            self._add(gathering, entry)
            gathering.tests += len(tests.parsed.symbols)
            gathering.extra_files += 1

            # One test file per changed file is enough to judge whether it is covered.
            break


def changed_files(diff: str) -> tuple[ChangedFile, ...]:
    """Which files a diff touches, and on which lines of the new revision."""
    files: list[ChangedFile] = []

    for patched in PatchSet(diff):
        lines: list[int] = []
        changes = 0

        for hunk in patched:
            for line in hunk:
                if line.is_added:
                    changes += 1
                    if line.target_line_no is not None:
                        lines.append(line.target_line_no)
                elif line.is_removed:
                    changes += 1
                elif line.is_context and line.target_line_no is not None:
                    lines.append(line.target_line_no)

        if not lines:
            # A pure deletion: the hunk header still says where it happened.
            lines = [hunk.target_start for hunk in patched]

        files.append(ChangedFile(path=patched.path, ranges=_ranges(lines), changes=changes))

    return tuple(files)


def _ranges(lines: list[int]) -> tuple[tuple[int, int], ...]:
    """Compress line numbers into the ranges they form."""
    if not lines:
        return ()

    ordered = sorted(set(lines))
    ranges: list[tuple[int, int]] = []
    first = previous = ordered[0]

    for line in ordered[1:]:
        if line == previous + 1:
            previous = line
            continue

        ranges.append((first, previous))
        first = previous = line

    ranges.append((first, previous))

    return tuple(ranges)


def skipped_path(path: str) -> bool:
    """Whether a path must never be sent anywhere: secrets, or generated noise."""
    lowered = path.casefold()
    name = lowered.rsplit("/", 1)[-1]

    if any(directory in lowered for directory in SKIPPED_DIRECTORIES):
        return True

    if lowered.endswith(SKIPPED_SUFFIXES) or name in SKIPPED_NAMES or name.startswith(".env"):
        return True

    return any(part in name for part in SKIPPED_NAME_PARTS)


def resolve_module(path: str, imported: ImportDTO, known_paths: tuple[str, ...]) -> str | None:
    """Map an import onto a path in the repository, when that can be told.

    Python writes a relative import with dots (``from ..pkg import x``) and
    JavaScript with a path (``../utils``); both are accepted, so the parser may
    report either shape. An absolute Python module resolves by its dotted path.
    """
    directory = path.rsplit("/", 1)[0] if "/" in path else ""

    if imported.relative:
        candidate = _relative_candidate(directory, imported.module)
    else:
        candidate = imported.module.replace(".", "/")

    if not candidate:
        return None

    # A specifier whose first segment exists in the tree is about this repository
    # (`revu.domain...` under a `src/` layout), so the file name may be matched too.
    # A bare package name (`react`) is not, and must not grab an unrelated file.
    head = candidate.split("/", 1)[0]
    belongs_here = any(known.startswith(f"{head}/") or f"/{head}/" in known for known in known_paths)

    return _first_existing(candidate, known_paths, allow_basename_match=belongs_here)


def _relative_candidate(directory: str, module: str) -> str:
    """Resolve a relative specifier against the directory of the importing file."""
    leading_dots = len(module) - len(module.lstrip("."))
    is_path_style = module.startswith("./") or module.startswith("../")
    base = directory

    if is_path_style:
        levels = module.count("../")
        tail = module.split("/")[-1]
    else:
        # Python: one dot means "this package", so only the extra dots climb up.
        levels = max(leading_dots - 1, 0)
        tail = module.lstrip(".").replace(".", "/")

    for _ in range(levels):
        base = base.rsplit("/", 1)[0] if "/" in base else ""

    return f"{base}/{tail}".strip("/") if tail else base


def _first_existing(
    candidate: str,
    known_paths: tuple[str, ...],
    *,
    allow_basename_match: bool = True,
) -> str | None:
    """The first path in the tree that a module specifier could mean."""
    options = [candidate, *(f"{candidate}{suffix}" for suffix in MODULE_SUFFIXES), f"{candidate}/__init__.py"]

    for option in options:
        if option in known_paths:
            return option

    if not allow_basename_match:
        return None

    # Last resort: the tree is authoritative about layout while the specifier is not
    # (a `src/` prefix, a `lib/` directory), so match on the file name too.
    stem = candidate.rsplit("/", 1)[-1]

    for known in known_paths:
        known_stem, _, known_suffix = known.rpartition(".")
        if known_stem.rsplit("/", 1)[-1] != stem:
            continue

        if f".{known_suffix}" in MODULE_SUFFIXES or known.endswith("/__init__.py"):
            return known

    return None


def test_candidates(path: str, known_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Test files that plausibly cover a changed file, the closest match first."""
    directory, _, filename = path.rpartition("/")
    stem, _, suffix = filename.rpartition(".")
    stem = stem or filename
    suffix = f".{suffix}" if suffix else ""

    # Both spellings occur in the wild: `service_test.go` and `ServiceTest.java`, and
    # only the first letter is uppercased, so `ReviewService` keeps its capitals.
    capitalised = stem[:1].upper() + stem[1:]
    wanted = {
        pattern.format(stem=variant, suffix=suffix).casefold()
        for pattern in TEST_PATTERNS
        for variant in (stem, capitalised)
    }

    matches = [known for known in known_paths if known.rsplit("/", 1)[-1].casefold() in wanted]

    # A test that sits next to the file it covers is the better bet.
    return tuple(sorted(matches, key=lambda known: (known.rpartition("/")[0] != directory, len(known))))
