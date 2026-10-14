"""Which grammar parses which file, and how each grammar spells a definition.

Every grammar is installed as an individual wheel (``tree-sitter-python`` and
friends) instead of through the aggregated ``tree-sitter-language-pack``: the pack
downloads grammars into a cache directory on first use, which breaks in the closed
networks this service is deployed in and makes the container write state on the
first parse. Individual wheels carry the compiled grammar inside the package, so
parsing is offline by construction.

The bindings are not uniform, so this module encodes what the installed wheels
actually expose (verified by importing and calling every package, tree-sitter
0.26):

* most packages expose ``language()``;
* ``tree-sitter-typescript`` exposes ``language_typescript()`` and
  ``language_tsx()``. The two grammars differ (tsx adds JSX), so ``.ts`` and
  ``.tsx`` are separate entries below;
* ``tree-sitter-ocaml`` exposes ``language_ocaml()``, ``language_ocaml_interface()``
  and ``language_ocaml_type()`` — there is no plain ``language()``, and the
  interface grammar for ``.mli`` is not the implementation grammar;
* ``tree-sitter-php`` exposes ``language_php()`` (full PHP: markup around ``<?php``
  is parsed as text) and ``language_php_only()`` (PHP with no markup allowed). A
  ``.php`` file may contain markup, so the full grammar is the one that matches
  the extension;
* ``tree-sitter-perl`` and ``tree-sitter-dockerfile`` still hand back a legacy
  ``int`` pointer rather than the capsule every other wheel returns; both forms
  are accepted by ``Language(...)``, the ``int`` one under a deprecation warning
  that we silence because it is their only entry point;
* ``Language.name`` is ``None`` for the ABI-14 grammars, so the label reported in
  :class:`ParsedFileDTO` is our own grammar key rather than the grammar's own name;
* the ABI-14 grammars are also the ones whose node types differ most from their
  documentation, which is why the tables below were read off real parse trees
  rather than off upstream docs.

The tables say how to read definitions out of a grammar: which node types start a
symbol, where the name and the body live, and which nodes carry calls and type
annotations. That keeps the walker in :mod:`tree_sitter_parser` generic — adding a
language means adding data, not a new branch.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import import_module
from typing import Final

from tree_sitter import Language

# --------------------------------------------------------------------------- #
# Grammar registry
# --------------------------------------------------------------------------- #

#: Grammar key -> ``(module, attribute)`` holding the language pointer.
#: Imported lazily: building 31 shared libraries at import time is exactly the
#: cost ``supports()`` must not pay.
_GRAMMAR_SOURCES: Final[Mapping[str, tuple[str, str]]] = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "go": ("tree_sitter_go", "language"),
    "java": ("tree_sitter_java", "language"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "c_sharp": ("tree_sitter_c_sharp", "language"),
    "php": ("tree_sitter_php", "language_php"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "swift": ("tree_sitter_swift", "language"),
    "scala": ("tree_sitter_scala", "language"),
    "elixir": ("tree_sitter_elixir", "language"),
    "lua": ("tree_sitter_lua", "language"),
    "perl": ("tree_sitter_perl", "language"),
    "dart": ("tree_sitter_dart", "language"),
    "bash": ("tree_sitter_bash", "language"),
    "sql": ("tree_sitter_sql", "language"),
    "html": ("tree_sitter_html", "language"),
    "css": ("tree_sitter_css", "language"),
    "hcl": ("tree_sitter_hcl", "language"),
    "yaml": ("tree_sitter_yaml", "language"),
    "json": ("tree_sitter_json", "language"),
    "make": ("tree_sitter_make", "language"),
    "zig": ("tree_sitter_zig", "language"),
    "haskell": ("tree_sitter_haskell", "language"),
    "ocaml": ("tree_sitter_ocaml", "language_ocaml"),
    "ocaml_interface": ("tree_sitter_ocaml", "language_ocaml_interface"),
    "dockerfile": ("tree_sitter_dockerfile", "language"),
}

#: Lower-case extension (including the dot) -> grammar key.
EXTENSION_TO_GRAMMAR: Final[Mapping[str, str]] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".rs": "rust",
    ".cs": "c_sharp",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".swift": "swift",
    ".scala": "scala",
    ".sc": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".dart": "dart",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".hcl": "hcl",
    ".tf": "hcl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".mk": "make",
    ".zig": "zig",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml_interface",
    ".dockerfile": "dockerfile",
}

#: Lower-case file name (no directory) -> grammar key, for the extension-less cases.
FILENAME_TO_GRAMMAR: Final[Mapping[str, str]] = {
    "makefile": "make",
    "dockerfile": "dockerfile",
}


def grammar_for_path(path: str) -> str | None:
    """The grammar key for a path, or ``None`` when no grammar claims it.

    Deliberately a pure string check so ``supports()`` never touches a grammar:
    the answer must be cheap enough to run for every file of a diff.
    """
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not name:
        return None

    by_name = FILENAME_TO_GRAMMAR.get(name)
    if by_name is not None:
        return by_name

    _, dot, extension = name.rpartition(".")
    if not dot:
        return None

    return EXTENSION_TO_GRAMMAR.get(f".{extension}")


@cache
def language_for(grammar: str) -> Language | None:
    """The built ``Language`` for a grammar key, or ``None`` when it will not load.

    Building a ``Language`` loads a shared library and parses the grammar's symbol
    tables; that is the expensive half, so the result is cached and shared across
    threads. Parsers built from it are not shared — see
    :class:`~revu.infrastructure.code_analysis.tree_sitter_parser.TreeSitterCodeParser`.
    """
    source = _GRAMMAR_SOURCES.get(grammar)
    if source is None:
        return None

    module_name, attribute = source
    try:
        pointer = getattr(import_module(module_name), attribute)()
    except Exception:
        # A missing or broken wheel must degrade to "this language cannot be
        # parsed", never to a failed review.
        return None

    with warnings.catch_warnings():
        # `tree-sitter-perl` and `tree-sitter-dockerfile` only expose the legacy
        # int pointer; the overload is deprecated, not removable.
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            return Language(pointer)
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# Per-language extraction tables
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DefinitionRule:
    """How one grammar spells a definition node."""

    kind: str = "function"
    """``class``, ``function``, or ``""`` for a scope-only container (Rust ``impl``)."""

    name_fields: tuple[str, ...] = ("name",)
    """Fields to read the name from, most specific first."""

    name_from_parent_fields: tuple[str, ...] = ()
    """Fallback name fields on the parent, for anonymous nodes (``const f = () => {}``)."""

    name_from_leading_labels: bool = False
    """Name from the leading identifier/string children (HCL block labels)."""

    name_first_argument: bool = False
    """Name from the first argument (Elixir ``def name(...)``)."""

    fixed_name: str = ""
    """Name that the grammar does not spell out (Swift ``init``)."""

    body_field: str = "body"
    """Field holding the body, whose start ends the signature."""

    body_via_first_child: bool = False
    """The body field lives on the single wrapper child (OCaml ``let_binding``)."""

    body_is_sibling: bool = False
    """The body is the next sibling, not a child (Dart signatures)."""

    owner_field: str = ""
    """Field naming the owner of a method (Go receiver, Rust ``impl`` type)."""

    nested_inside_definition: bool = False
    """Skip this node when a definition node wraps it (Dart ``function_signature``)."""

    requires_field: str = ""
    """Match only when the node carries this field (Haskell reuses ``function`` for types)."""


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Everything the generic walker needs to read one grammar.

    The mappings are built as literals and never mutated; they are not frozen
    only because frozen dataclasses cannot hold a literal ``dict`` default.
    """

    definitions: Mapping[str, DefinitionRule] = field(default_factory=dict)
    """Node type -> rule for declarations that become symbols."""

    call_definitions: Mapping[str, DefinitionRule] = field(default_factory=dict)
    """Callee text -> rule for grammars that spell definitions as calls (Elixir)."""

    body_kinds: frozenset[str] = frozenset()
    """Node types that start a body when no field marks one."""

    wrappers: frozenset[str] = frozenset()
    """Transparent nodes whose child definition should include them (decorators)."""

    call_kinds: frozenset[str] = frozenset()
    """Node types that are call expressions, for ``referenced_names``."""

    callee_fields: tuple[str, ...] = ("function",)
    """Fields holding the callee; the first named child is the fallback."""

    annotation_kinds: frozenset[str] = frozenset()
    """Node types in type position, for ``referenced_names``."""

    import_style: str = ""
    """``python`` or ``esm`` for the two import syntaxes extracted precisely."""


_JAVASCRIPT_DEFINITIONS: Final[Mapping[str, DefinitionRule]] = {
    "class_declaration": DefinitionRule(kind="class"),
    "method_definition": DefinitionRule(),
    "function_declaration": DefinitionRule(),
    "generator_function_declaration": DefinitionRule(),
    "function_expression": DefinitionRule(name_from_parent_fields=("name",)),
    "arrow_function": DefinitionRule(name_from_parent_fields=("name", "left")),
}

_TYPESCRIPT_DEFINITIONS: Final[Mapping[str, DefinitionRule]] = {
    **_JAVASCRIPT_DEFINITIONS,
    "abstract_class_declaration": DefinitionRule(kind="class"),
    "interface_declaration": DefinitionRule(kind="class"),
    "enum_declaration": DefinitionRule(kind="class"),
    "type_alias_declaration": DefinitionRule(kind="class"),
    "function_signature": DefinitionRule(),
    "method_signature": DefinitionRule(),
    "abstract_method_signature": DefinitionRule(),
}

_C_DEFINITIONS: Final[Mapping[str, DefinitionRule]] = {
    "function_definition": DefinitionRule(name_fields=("declarator",)),
    "struct_specifier": DefinitionRule(kind="class"),
    "union_specifier": DefinitionRule(kind="class"),
    "enum_specifier": DefinitionRule(kind="class"),
}


def _elixir_rule(kind: str) -> DefinitionRule:
    return DefinitionRule(kind=kind, name_first_argument=True)


SPECS: Final[Mapping[str, LanguageSpec]] = {
    "python": LanguageSpec(
        definitions={
            "class_definition": DefinitionRule(kind="class"),
            "function_definition": DefinitionRule(),
        },
        wrappers=frozenset({"decorated_definition"}),
        call_kinds=frozenset({"call"}),
        annotation_kinds=frozenset({"type"}),
        import_style="python",
    ),
    "javascript": LanguageSpec(
        definitions=_JAVASCRIPT_DEFINITIONS,
        body_kinds=frozenset({"statement_block", "class_body"}),
        call_kinds=frozenset({"call_expression", "new_expression"}),
        callee_fields=("function", "constructor"),
        import_style="esm",
    ),
    "typescript": LanguageSpec(
        definitions=_TYPESCRIPT_DEFINITIONS,
        body_kinds=frozenset({"statement_block", "class_body", "interface_body", "enum_body"}),
        call_kinds=frozenset({"call_expression", "new_expression"}),
        callee_fields=("function", "constructor"),
        annotation_kinds=frozenset({"type_annotation", "type_identifier"}),
        import_style="esm",
    ),
    "tsx": LanguageSpec(
        definitions=_TYPESCRIPT_DEFINITIONS,
        body_kinds=frozenset({"statement_block", "class_body", "interface_body", "enum_body"}),
        call_kinds=frozenset({"call_expression", "new_expression"}),
        callee_fields=("function", "constructor"),
        annotation_kinds=frozenset({"type_annotation", "type_identifier"}),
        import_style="esm",
    ),
    "go": LanguageSpec(
        definitions={
            "function_declaration": DefinitionRule(),
            "method_declaration": DefinitionRule(owner_field="receiver"),
            "type_spec": DefinitionRule(kind="class"),
        },
        body_kinds=frozenset({"block"}),
        call_kinds=frozenset({"call_expression"}),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "java": LanguageSpec(
        definitions={
            "class_declaration": DefinitionRule(kind="class"),
            "interface_declaration": DefinitionRule(kind="class"),
            "enum_declaration": DefinitionRule(kind="class"),
            "annotation_type_declaration": DefinitionRule(kind="class"),
            "record_declaration": DefinitionRule(kind="class"),
            "method_declaration": DefinitionRule(),
            "constructor_declaration": DefinitionRule(),
            "compact_constructor_declaration": DefinitionRule(),
        },
        body_kinds=frozenset({"block", "constructor_body", "class_body", "interface_body", "enum_body"}),
        call_kinds=frozenset({"method_invocation", "object_creation_expression", "explicit_constructor_invocation"}),
        callee_fields=("name", "type", "constructor"),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "kotlin": LanguageSpec(
        definitions={
            "class_declaration": DefinitionRule(kind="class"),
            "object_declaration": DefinitionRule(kind="class"),
            "function_declaration": DefinitionRule(),
            "secondary_constructor": DefinitionRule(),
        },
        body_kinds=frozenset({"function_body", "class_body", "enum_class_body"}),
        call_kinds=frozenset({"call_expression"}),
        callee_fields=(),
        annotation_kinds=frozenset({"user_type"}),
    ),
    "ruby": LanguageSpec(
        definitions={
            "class": DefinitionRule(kind="class"),
            "module": DefinitionRule(kind="class"),
            "method": DefinitionRule(),
            "singleton_method": DefinitionRule(),
        },
        body_kinds=frozenset({"body_statement"}),
        call_kinds=frozenset({"call"}),
        callee_fields=("method",),
    ),
    "rust": LanguageSpec(
        definitions={
            "function_item": DefinitionRule(),
            "function_signature_item": DefinitionRule(),
            "struct_item": DefinitionRule(kind="class"),
            "enum_item": DefinitionRule(kind="class"),
            "union_item": DefinitionRule(kind="class"),
            "trait_item": DefinitionRule(kind="class"),
            # `impl` is not a type but it names the owner of every method inside.
            "impl_item": DefinitionRule(kind="", owner_field="type"),
        },
        body_kinds=frozenset({"block", "declaration_list", "field_declaration_list", "enum_variant_list"}),
        call_kinds=frozenset({"call_expression", "macro_invocation"}),
        callee_fields=("function", "macro"),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "c": LanguageSpec(
        definitions=_C_DEFINITIONS,
        body_kinds=frozenset({"compound_statement", "field_declaration_list", "enumerator_list"}),
        call_kinds=frozenset({"call_expression"}),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "cpp": LanguageSpec(
        definitions={**_C_DEFINITIONS, "class_specifier": DefinitionRule(kind="class")},
        wrappers=frozenset({"template_declaration"}),
        body_kinds=frozenset({"compound_statement", "field_declaration_list", "enumerator_list"}),
        call_kinds=frozenset({"call_expression", "new_expression"}),
        callee_fields=("function", "type", "constructor"),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "c_sharp": LanguageSpec(
        definitions={
            "class_declaration": DefinitionRule(kind="class"),
            "interface_declaration": DefinitionRule(kind="class"),
            "struct_declaration": DefinitionRule(kind="class"),
            "enum_declaration": DefinitionRule(kind="class"),
            "record_declaration": DefinitionRule(kind="class"),
            "method_declaration": DefinitionRule(),
            "constructor_declaration": DefinitionRule(),
            "destructor_declaration": DefinitionRule(),
            "local_function_statement": DefinitionRule(),
        },
        body_kinds=frozenset({"block", "declaration_list", "arrow_expression_clause", "enum_member_declaration_list"}),
        call_kinds=frozenset(
            {"invocation_expression", "object_creation_expression", "implicit_object_creation_expression"}
        ),
        callee_fields=("function", "type"),
    ),
    "php": LanguageSpec(
        definitions={
            "class_declaration": DefinitionRule(kind="class"),
            "interface_declaration": DefinitionRule(kind="class"),
            "trait_declaration": DefinitionRule(kind="class"),
            "enum_declaration": DefinitionRule(kind="class"),
            "function_definition": DefinitionRule(),
            "method_declaration": DefinitionRule(),
        },
        body_kinds=frozenset({"compound_statement", "declaration_list", "enum_declaration_list"}),
        call_kinds=frozenset(
            {
                "function_call_expression",
                "member_call_expression",
                "scoped_call_expression",
                "nullsafe_member_call_expression",
                "object_creation_expression",
            }
        ),
        callee_fields=("function", "name"),
    ),
    "swift": LanguageSpec(
        definitions={
            "class_declaration": DefinitionRule(kind="class"),
            "protocol_declaration": DefinitionRule(kind="class"),
            "function_declaration": DefinitionRule(),
            "protocol_function_declaration": DefinitionRule(),
            "init_declaration": DefinitionRule(fixed_name="init"),
            "deinit_declaration": DefinitionRule(fixed_name="deinit"),
        },
        body_kinds=frozenset({"function_body", "class_body", "protocol_body", "enum_class_body"}),
        call_kinds=frozenset({"call_expression"}),
        callee_fields=(),
        annotation_kinds=frozenset({"user_type", "type_identifier"}),
    ),
    "scala": LanguageSpec(
        definitions={
            "class_definition": DefinitionRule(kind="class"),
            "object_definition": DefinitionRule(kind="class"),
            "trait_definition": DefinitionRule(kind="class"),
            "enum_definition": DefinitionRule(kind="class"),
            "function_definition": DefinitionRule(),
        },
        body_kinds=frozenset({"template_body", "block"}),
        call_kinds=frozenset({"call_expression"}),
        callee_fields=("function", "name"),
        annotation_kinds=frozenset({"type_identifier", "stable_type_identifier"}),
    ),
    "elixir": LanguageSpec(
        # Elixir has no definition nodes: `defmodule`, `def` and friends are calls,
        # so the table is keyed by the callee text instead of by node type.
        call_definitions={
            "defmodule": _elixir_rule("class"),
            "defprotocol": _elixir_rule("class"),
            "def": _elixir_rule("function"),
            "defp": _elixir_rule("function"),
            "defmacro": _elixir_rule("function"),
            "defmacrop": _elixir_rule("function"),
        },
        body_kinds=frozenset({"do_block"}),
        call_kinds=frozenset({"call"}),
        callee_fields=("target",),
    ),
    "lua": LanguageSpec(
        definitions={"function_declaration": DefinitionRule()},
        body_kinds=frozenset({"block"}),
        call_kinds=frozenset({"function_call"}),
        callee_fields=("name",),
    ),
    "perl": LanguageSpec(
        definitions={"subroutine_declaration_statement": DefinitionRule()},
        body_kinds=frozenset({"block"}),
        call_kinds=frozenset(
            {"function_call_expression", "method_call_expression", "ambiguous_function_call_expression"}
        ),
        callee_fields=("function", "method"),
    ),
    "dart": LanguageSpec(
        definitions={
            "class_definition": DefinitionRule(kind="class"),
            "mixin_declaration": DefinitionRule(kind="class"),
            "extension_declaration": DefinitionRule(kind="class"),
            "enum_declaration": DefinitionRule(kind="class"),
            # Dart splits a declaration into a signature node and a sibling body
            # node, and nests the signature inside the method signature wrapper.
            "method_signature": DefinitionRule(body_is_sibling=True),
            "function_signature": DefinitionRule(body_is_sibling=True, nested_inside_definition=True),
            "local_function_declaration": DefinitionRule(body_is_sibling=True),
        },
        body_kinds=frozenset({"function_body"}),
        annotation_kinds=frozenset({"type_identifier"}),
    ),
    "bash": LanguageSpec(
        definitions={"function_definition": DefinitionRule()},
        body_kinds=frozenset({"compound_statement"}),
        call_kinds=frozenset({"command"}),
        callee_fields=("name",),
    ),
    "sql": LanguageSpec(
        definitions={
            "create_table": DefinitionRule(kind="class"),
            "create_view": DefinitionRule(kind="class"),
            "create_materialized_view": DefinitionRule(kind="class"),
            "create_index": DefinitionRule(kind="class"),
            "create_schema": DefinitionRule(kind="class"),
            "create_type": DefinitionRule(kind="class"),
            "create_function": DefinitionRule(),
        },
        call_kinds=frozenset({"invocation"}),
        callee_fields=(),
    ),
    # CSS, HCL and Makefile have no functions or classes, so their nearest
    # equivalent declaration takes the class slot: a rule set, a labelled block
    # and a make rule are the units a reviewer reasons about.
    "css": LanguageSpec(
        definitions={
            "rule_set": DefinitionRule(kind="class"),
            "keyframes_statement": DefinitionRule(kind="class"),
        },
        body_kinds=frozenset({"block"}),
        call_kinds=frozenset({"call_expression"}),
        callee_fields=(),
    ),
    "hcl": LanguageSpec(
        definitions={"block": DefinitionRule(kind="class", name_from_leading_labels=True)},
        body_kinds=frozenset({"body"}),
        call_kinds=frozenset({"function_call"}),
        callee_fields=(),
    ),
    "make": LanguageSpec(
        definitions={"rule": DefinitionRule(kind="class")},
        body_kinds=frozenset({"recipe"}),
    ),
    "zig": LanguageSpec(
        definitions={"function_declaration": DefinitionRule()},
        body_kinds=frozenset({"block"}),
        call_kinds=frozenset({"call_expression", "builtin_function"}),
        callee_fields=(),
    ),
    "haskell": LanguageSpec(
        definitions={
            # The grammar's `function` node is both a definition (it has a `match`)
            # and a function type inside a signature (it has `parameter`/`result`),
            # so the rule demands the field only a definition carries.
            "function": DefinitionRule(requires_field="match"),
            "data_type": DefinitionRule(kind="class"),
            "newtype": DefinitionRule(kind="class"),
            "type_synonym": DefinitionRule(kind="class"),
            "class": DefinitionRule(kind="class"),
        },
        body_kinds=frozenset({"match", "class_declarations"}),
        call_kinds=frozenset({"apply"}),
    ),
    "ocaml": LanguageSpec(
        definitions={
            "value_definition": DefinitionRule(name_fields=("pattern",), body_via_first_child=True),
            "type_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "module_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "class_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "method_definition": DefinitionRule(),
        },
        body_kinds=frozenset({"structure", "object_expression"}),
        call_kinds=frozenset({"application_expression"}),
        annotation_kinds=frozenset({"type_constructor"}),
    ),
    "ocaml_interface": LanguageSpec(
        definitions={
            "value_specification": DefinitionRule(),
            "type_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "module_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "class_definition": DefinitionRule(kind="class", body_via_first_child=True),
            "method_specification": DefinitionRule(),
        },
        call_kinds=frozenset({"application_expression"}),
        annotation_kinds=frozenset({"type_constructor"}),
    ),
    # Markup and data files declare no callable unit, so they are parsed for their
    # language label and contribute nothing else; a diff hunk is the whole context
    # a reviewer needs there anyway.
    "html": LanguageSpec(),
    "yaml": LanguageSpec(),
    "json": LanguageSpec(),
    "dockerfile": LanguageSpec(),
}
