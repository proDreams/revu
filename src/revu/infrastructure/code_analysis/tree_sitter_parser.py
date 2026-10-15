"""A tree-sitter implementation of :class:`CodeParserProtocol`.

The walker here is generic on purpose: every language-specific fact lives in the
tables of :mod:`revu.infrastructure.code_analysis.languages`, so a new grammar is
data, not another branch. The two structures that make that possible are

* the *definition stack* — a class names its methods, everything else resets the
  owner to empty, which is what turns a nested ``def`` inside a method back into a
  plain function, and
* one *body* lookup that works for grammars which mark a body with a field, a
  node type, a sibling, or a field one wrapper down.

Parsing must never raise: a review of Java should not fail because one file in the
diff is a broken React component. Everything below therefore degrades to an empty
:class:`ParsedFileDTO` instead of propagating a grammar error.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

from tree_sitter import Language, Node, Parser

from revu.application.config import get_logger
from revu.domain.entities.dto.parsed_file_dto import ImportDTO, ParsedFileDTO, SymbolDTO
from revu.infrastructure.code_analysis.languages import (
    SPECS,
    DefinitionRule,
    LanguageSpec,
    grammar_for_path,
    language_for,
)

logger = get_logger(name=__name__)

#: Node types whose text is a name, across all the grammars we carry. A union is
#: enough: a grammar only ever produces its own node types, and no grammar uses one
#: of these names for something that is not a name.
_NAME_NODE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "alias",
        "bareword",
        "class_name",
        "constant",
        "constructor",
        "field_identifier",
        "field_name",
        "function",
        "function_name",
        "id_name",
        "identifier",
        "keyframes_name",
        "method_name",
        "module_name",
        "name",
        "namespace_identifier",
        "package_identifier",
        "property_identifier",
        "simple_identifier",
        "tag_name",
        "type_constructor",
        "type_identifier",
        "value_name",
        "variable",
        "word",
    }
)

#: Names that are already qualified (``M.save``, ``Repo::save``, ``a.b.c``): their
#: whole text is the name, so the walker must not descend to the last segment.
_QUALIFIED_NAME_NODE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "dot_index_expression",
        "member_expression",
        "qualified_identifier",
        "scoped_identifier",
    }
)

#: Fields a declarator hides its identifier behind (C ``function_declarator``).
_DECLARATOR_FIELDS: Final[tuple[str, ...]] = ("declarator", "name", "field", "property", "pattern")

#: Node kinds that can name an owning type, most specific first.
_OWNER_NODE_KINDS: Final[tuple[str, ...]] = (
    "type_identifier",
    "simple_identifier",
    "type_constructor",
    "user_type",
    "name",
    "identifier",
    "constant",
)

#: Node kinds that may carry an HCL-style leading label.
_LABEL_NODE_KINDS: Final[frozenset[str]] = frozenset({"bareword", "identifier", "string", "string_lit", "word"})

_QUOTES: Final[str] = "\"'`"


def _slice(data: bytes, start: int, end: int) -> str:
    return data[start:end].decode("utf-8", errors="replace")


def _text(data: bytes, node: Node | None) -> str:
    if node is None:
        return ""

    return _slice(data, node.start_byte, node.end_byte)


def _clean(text: str) -> str:
    """Strip whitespace and the quotes some grammars keep in a name or a path."""
    cleaned = text.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in _QUOTES:
        cleaned = cleaned[1:-1]

    return cleaned.strip()


def _first_of_kind(node: Node, kinds: frozenset[str]) -> Node | None:
    """The first node of a kind in document order, the node itself included.

    Walked with an explicit stack rather than by recursion: a generated tree can be
    as deep as the source is nested, and a file with a call chain a thousand calls
    long would otherwise exhaust the interpreter's stack — which `parse` used to
    swallow, leaving the file silently unparsed.
    """
    stack: list[Node] = [node]

    while stack:
        current = stack.pop()

        if current.type in kinds:
            return current

        stack.extend(reversed(current.named_children))

    return None


def _last_of_kind(node: Node, kinds: frozenset[str]) -> Node | None:
    """The rightmost node of a kind, which is how an attribute chain is flattened."""
    stack: list[Node] = [node]

    while stack:
        current = stack.pop()

        if current.type in kinds:
            return current

        # Children in document order, so the last one is popped first.
        stack.extend(current.named_children)

    return None


def _all_of_kind(node: Node, kinds: frozenset[str]) -> Iterator[Node]:
    """Every node of a kind in document order, without a frame per level."""
    stack: list[Node] = [node]

    while stack:
        current = stack.pop()

        if current.type in kinds:
            yield current

        stack.extend(reversed(current.named_children))


def _field_name(data: bytes, node: Node) -> str:
    """The name a node holds, descending declarators such as C's ``function_declarator``."""
    if node.type in _NAME_NODE_KINDS or node.type in _QUALIFIED_NAME_NODE_KINDS:
        return _clean(_text(data, node))

    for field_name in _DECLARATOR_FIELDS:
        child = node.child_by_field_name(field_name)
        if child is not None:
            name = _field_name(data, child)
            if name:
                return name

    return ""


def _definition_name(data: bytes, node: Node, rule: DefinitionRule) -> str:
    """The name of a definition node, trying every spelling a grammar may use."""
    if rule.fixed_name:
        return rule.fixed_name

    if rule.name_from_leading_labels:
        labels = []
        for label in node.named_children:
            if label.type not in _LABEL_NODE_KINDS:
                break
            labels.append(_clean(_text(data, label)))
        if labels:
            return ".".join(labels)

    if rule.name_first_argument:
        # Elixir: `def save(x)` nests the name in a call, `defmodule Repo` is an alias,
        # and the argument list is a plain child rather than a field.
        arguments = node.child_by_field_name("arguments") or _first_of_kind(node, frozenset({"arguments"}))
        first = arguments.named_children[0] if arguments is not None and arguments.named_children else None
        if first is not None:
            target = first.child_by_field_name("target") if first.type == "call" else None
            return _clean(_text(data, target if target is not None else first))

    for field_name in rule.name_fields:
        child = node.child_by_field_name(field_name)
        if child is not None:
            name = _field_name(data, child)
            if name:
                return name

    parent = node.parent
    if parent is not None:
        for field_name in rule.name_from_parent_fields:
            sibling = parent.child_by_field_name(field_name)
            if sibling is not None:
                name = _clean(_text(data, sibling))
                if name:
                    return name

    # Some grammars put the name one level down: Dart's `method_signature` wraps the
    # `function_signature` that owns it, SQL's `create_table` wraps `object_reference`.
    for child in node.named_children:
        for field_name in rule.name_fields:
            grandchild = child.child_by_field_name(field_name)
            if grandchild is not None:
                return _clean(_text(data, grandchild))

    return _clean(_text(data, _first_of_kind(node, _NAME_NODE_KINDS)))


def _owner_name(data: bytes, node: Node | None) -> str:
    """The type a method belongs to, for grammars that declare it next to the method."""
    if node is None:
        return ""

    for kind in _OWNER_NODE_KINDS:
        found = _first_of_kind(node, frozenset({kind}))
        if found is not None:
            return _clean(_text(data, found))

    return ""


def _body_node(node: Node, rule: DefinitionRule, spec: LanguageSpec) -> Node | None:
    if rule.body_field:
        body = node.child_by_field_name(rule.body_field)
        if body is not None:
            return body

    for child in node.named_children:
        if child.type in spec.body_kinds:
            return child

    if rule.body_via_first_child:
        # OCaml wraps every binding in a child that owns the `body` field.
        for child in node.named_children:
            body = child.child_by_field_name(rule.body_field) if rule.body_field else None
            if body is not None:
                return body

    if rule.body_is_sibling:
        sibling = node.next_named_sibling
        if sibling is not None and sibling.type in spec.body_kinds:
            return sibling

    return None


def _signature(data: bytes, node: Node, body: Node | None) -> str:
    """The declaration header: from the node start up to its body, never the body."""
    if body is not None and body.start_byte > node.start_byte:
        return _slice(data, node.start_byte, body.start_byte).rstrip()

    # No body to stop at (an abstract method, a type alias): the declaration is
    # whatever its first line says, and the rest would be the body.
    lines = _slice(data, node.start_byte, node.end_byte).splitlines()

    return lines[0].rstrip() if lines else ""


def _body_text(data: bytes, node: Node, body: Node | None) -> str:
    end = node.end_byte
    if body is not None and body.end_byte > end:
        end = body.end_byte

    return _slice(data, node.start_byte, end).rstrip()


def _callee_node(node: Node, fields: tuple[str, ...]) -> Node | None:
    for field_name in fields:
        child = node.child_by_field_name(field_name)
        if child is not None:
            return child

    return node.named_children[0] if node.named_children else None


def _callee_name(data: bytes, node: Node | None) -> str:
    """The last segment of a callee, so ``Repo().save(1)`` yields ``save``."""
    if node is None:
        return ""

    return _clean(_text(data, _last_of_kind(node, _NAME_NODE_KINDS)))


# --------------------------------------------------------------------------- #
# Imports: Python and the JS/TS module syntaxes are the only two extracted.
#
# They are the two the reviewer needs to reason about file boundaries: Python's
# absolute/relative split decides which package a name comes from, and ESM's
# relative specifier is the only import form where the target is a file we may be
# reviewing in the same diff. Java, Go, Rust and friends import by package or crate
# path that resolves through a build file we do not read, `#include` pulls in a
# header rather than a module, and Ruby's `require` is a plain call; guessing there
# would produce references the review cannot verify, so those stay empty.
# --------------------------------------------------------------------------- #


def _python_imports(data: bytes, node: Node) -> Iterator[ImportDTO]:
    if node.type == "import_statement":
        # `import x.y, z as w`: one DTO per module, because each one is bound separately.
        for child in node.children_by_field_name("name"):
            if child.type == "aliased_import":
                yield ImportDTO(
                    module=_text(data, child.child_by_field_name("name")),
                    names=(_text(data, child.child_by_field_name("alias")),),
                )
                continue
            yield ImportDTO(module=_text(data, child))
        return

    if node.type != "import_from_statement":
        return

    module_node = node.child_by_field_name("module_name")
    relative = module_node is not None and module_node.type == "relative_import"

    names = []
    for child in node.children_by_field_name("name"):
        if child.type == "aliased_import":
            names.append(_text(data, child.child_by_field_name("alias")))
        else:
            names.append(_text(data, child))

    if not names and any(child.type == "wildcard_import" for child in node.children):
        names.append("*")

    yield ImportDTO(module=_text(data, module_node), names=tuple(names), relative=relative)


def _esm_names(data: bytes, node: Node) -> tuple[str, ...]:
    clause = _first_of_kind(node, frozenset({"import_clause"}))
    if clause is None:
        return ()

    names = []
    for child in clause.named_children:
        if child.type == "identifier":
            names.append(_clean(_text(data, child)))
        elif child.type == "namespace_import":
            names.extend(_clean(_text(data, found)) for found in _all_of_kind(child, _NAME_NODE_KINDS))
        elif child.type == "named_imports":
            for specifier in child.named_children:
                alias = specifier.child_by_field_name("alias")
                target = alias if alias is not None else specifier.child_by_field_name("name")
                names.append(_clean(_text(data, target)))

    return tuple(names)


def _esm_imports(data: bytes, node: Node) -> Iterator[ImportDTO]:
    if node.type == "import_statement":
        module = _clean(_text(data, node.child_by_field_name("source")))
        if module:
            yield ImportDTO(module=module, names=_esm_names(data, node), relative=module.startswith("."))
        return

    if node.type != "call_expression":
        return

    # `require("./x")` and the dynamic `import("./x")` are the CommonJS forms of the
    # same edge, and appear often enough in reviewed code to be worth the two lines.
    # The dynamic import has a keyword node as its callee, so its own text is the name.
    callee = _callee_node(node, ("function",))
    callee_name = _callee_name(data, callee) or _clean(_text(data, callee))
    if callee_name not in {"require", "import"}:
        return

    arguments = node.child_by_field_name("arguments")
    if arguments is None or not arguments.named_children:
        return

    module = _clean(_text(data, arguments.named_children[0]))
    if module:
        yield ImportDTO(module=module, relative=module.startswith("."))


def _imports(data: bytes, node: Node, spec: LanguageSpec) -> Iterator[ImportDTO]:
    if spec.import_style == "python":
        yield from _python_imports(data, node)
    elif spec.import_style == "esm":
        yield from _esm_imports(data, node)


# --------------------------------------------------------------------------- #
# The walker
# --------------------------------------------------------------------------- #


class _FileWalker:
    """Collects symbols, imports and referenced names from one parsed file."""

    __slots__ = ("_data", "_spec", "_symbols", "_imports", "_referenced")

    def __init__(self, data: bytes, spec: LanguageSpec) -> None:
        self._data = data
        self._spec = spec
        self._symbols: list[SymbolDTO] = []
        self._imports: list[ImportDTO] = []
        self._referenced: set[str] = set()

    def run(self, root: Node) -> tuple[tuple[SymbolDTO, ...], tuple[ImportDTO, ...], frozenset[str]]:
        self._visit(root, "")

        return tuple(self._symbols), tuple(self._imports), frozenset(self._referenced)

    def _rule_for(self, node: Node) -> DefinitionRule | None:
        spec = self._spec
        rule = spec.definitions.get(node.type)
        if rule is not None:
            if rule.nested_inside_definition and node.parent is not None and node.parent.type in spec.definitions:
                return None
            if rule.requires_field and node.child_by_field_name(rule.requires_field) is None:
                return None
            return rule

        if spec.call_definitions and node.type == "call":
            return spec.call_definitions.get(_text(self._data, node.child_by_field_name("target")))

        return None

    def _wrapper_definition(self, node: Node) -> tuple[Node, DefinitionRule] | None:
        """The definition a decorator or template node wraps, and its rule.

        The wrapper never contains another declaration, so the first child that is
        one is the one to widen: decorators and template parameters have none. The
        child is asked through `_rule_for`, like every other node, so a rule that
        only applies in some positions — nested definitions, rules that require a
        field — is not applied here on weaker terms. The rule comes back with the
        node rather than being looked up twice.
        """
        if node.type not in self._spec.wrappers:
            return None

        for child in node.named_children:
            rule = self._rule_for(child)

            if rule is not None:
                return child, rule

        # Every wrapper a grammar produces holds the definition it wraps. A tree
        # recovered from a syntax error could still be one without, so the walk is
        # not allowed to assume it — but no grammar we carry produces one.
        return None  # pragma: no cover - defensive; no grammar here produces it

    def _visit(self, root: Node, owner: str) -> None:
        """Walk the tree in document order, with a stack instead of recursion.

        The same order the recursive version produced, node by node: a node is
        handled before its children and children are visited in document order.
        Only the shape changed, because the depth of a generated tree is the depth
        of whatever the author nested, and no file should be able to exhaust the
        interpreter's stack.
        """
        stack: list[tuple[Node, str]] = [(root, owner)]

        while stack:
            node, owner_here = stack.pop()
            rule = self._rule_for(node)
            definition = node
            symbol_range = node

            if rule is None:
                wrapped = self._wrapper_definition(node)
                if wrapped is None:
                    self._references(node)
                    self._imports.extend(_imports(self._data, node, self._spec))
                    stack.extend((child, owner_here) for child in reversed(node.named_children))
                    continue
                # A decorator or a template wraps the definition it belongs to: the
                # symbol spans the wrapper, its body is read from the inner node.
                definition, rule = wrapped

            child_owner = self._emit(rule, definition, symbol_range, owner_here)
            self._references(node)
            self._imports.extend(_imports(self._data, node, self._spec))

            for child in reversed(node.named_children):
                # Nodes are handles, not stable objects, so identity is `==`, not `is`.
                if child == definition and definition != node:
                    # The wrapper already accounted for its definition node; only its
                    # contents still need walking, as children of the emitted symbol.
                    stack.extend((grandchild, child_owner) for grandchild in reversed(child.named_children))
                    continue
                stack.append((child, child_owner))

    def _emit(self, rule: DefinitionRule, definition: Node, symbol_range: Node, owner: str) -> str:
        """Append a symbol and return the owner name its children inherit."""
        name = _definition_name(self._data, definition, rule)
        receiver = ""
        if rule.owner_field:
            receiver = _owner_name(self._data, definition.child_by_field_name(rule.owner_field))

        if not rule.kind:
            # A scope-only container such as Rust's `impl`: it names the methods
            # inside and is not itself a declaration a reviewer would comment on.
            return receiver or name or owner

        if not name:
            return owner

        kind = rule.kind
        if kind == "function" and (owner or receiver):
            kind = "method"

        qualified_name = f"{owner or receiver}.{name}" if kind == "method" else name
        body_node = _body_node(definition, rule, self._spec)
        body = _body_text(self._data, symbol_range, body_node)
        start_line = symbol_range.start_point.row + 1

        self._symbols.append(
            SymbolDTO(
                kind=kind,
                name=name,
                qualified_name=qualified_name,
                start_line=start_line,
                # Derived from the body so lines and text can never disagree, even
                # for a grammar whose node includes the trailing newline.
                end_line=start_line + body.count("\n"),
                signature=_signature(self._data, symbol_range, body_node),
                body=body,
            )
        )

        # Only a class keeps an owner: a nested `def` inside a method is a function
        # again, while a method of a class is `Class.method`.
        return name if kind == "class" else ""

    def _references(self, node: Node) -> None:
        if node.type in self._spec.call_kinds:
            name = _callee_name(self._data, _callee_node(node, self._spec.callee_fields))
            if name:
                self._referenced.add(name)

        if node.type in self._spec.annotation_kinds:
            for found in _all_of_kind(node, _NAME_NODE_KINDS):
                name = _clean(_text(self._data, found))
                if name:
                    self._referenced.add(name)


class TreeSitterCodeParser:
    """Parse a source file into symbols, imports and referenced names.

    Grammar objects are cached inside :mod:`languages`; a ``Parser`` is created per
    call because one holds parsing state and is not safe to share between threads.
    """

    def supports(self, path: str) -> bool:
        return grammar_for_path(path) is not None

    def parse(self, path: str, source: str) -> ParsedFileDTO:
        grammar = grammar_for_path(path)
        if grammar is None:
            return ParsedFileDTO()

        language: Language | None = language_for(grammar)
        if language is None:
            return ParsedFileDTO()

        spec = SPECS[grammar]
        if not (
            spec.definitions or spec.call_definitions or spec.call_kinds or spec.annotation_kinds or spec.import_style
        ):
            # Nothing to walk for, so a data file costs a lookup and no tree walk.
            return ParsedFileDTO(language=grammar)

        # `errors="replace"` keeps a lone surrogate from raising before the parser
        # ever sees the text.
        data = source.encode("utf-8", errors="replace")

        try:
            # The parser is held in a local until the walk is over: `Tree` keeps its
            # language alive, but the parser it came from is cheap to keep and this
            # is not a place to be clever about lifetimes.
            parser = Parser(language)
            tree = parser.parse(data)
            symbols, imports, referenced = _FileWalker(data, spec).run(tree.root_node)
        except Exception:
            # Recovery is the grammar's job, but a wheel that fails outright must
            # still leave the review running: the file is simply unparsed. Saying so
            # matters — a silent `ParsedFileDTO()` is indistinguishable, at the call
            # site, from a file with nothing in it, and that is how a deep file was
            # skipped without anyone noticing.
            logger.warning("could not parse %s; the file is left out of the context", path, exc_info=True)

            return ParsedFileDTO()

        return ParsedFileDTO(
            language=grammar,
            symbols=symbols,
            imports=imports,
            referenced_names=referenced,
        )
