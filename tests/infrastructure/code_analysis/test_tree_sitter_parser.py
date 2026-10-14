"""What the tree-sitter parser extracts, one real snippet per grammar.

The snippets are small on purpose: every assertion here is about an exact line
number, signature or import, and a shorter file makes a failure readable.
"""

from __future__ import annotations

import pytest
from tree_sitter import Parser

from revu.domain.entities.dto.parsed_file_dto import ImportDTO, ParsedFileDTO
from revu.infrastructure.code_analysis import tree_sitter_parser
from revu.infrastructure.code_analysis.languages import (
    EXTENSION_TO_GRAMMAR,
    FILENAME_TO_GRAMMAR,
    language_for,
)
from revu.infrastructure.code_analysis.tree_sitter_parser import (
    TreeSitterCodeParser,
    _callee_name,
    _field_name,
    _owner_name,
    _text,
)

pytestmark = pytest.mark.unit

_parser = TreeSitterCodeParser()

PYTHON_SOURCE = """import os
import x.y as z
from a.b import c, d
from a.b import c as renamed
from . import q
from .rel import e
from a import *

class Repo(Base):
    def save(self, x: int) -> None:
        self.x = helper(x)

    @property
    def value(self):
        return Repo().load(1)

def plain(a):
    return a

def outer():
    def inner():
        pass
"""

JAVASCRIPT_SOURCE = """import d, { a as b } from "./m.js";
import * as ns from "pkg";
import "./side-effect.js";
const f = (x) => { return helper(x); };
class C {
  m() { return a(); }
}
function g() { require("./cjs.js"); import("./dyn.js"); require(); require(""); }
(function () {})();
"""

TYPESCRIPT_SOURCE = """import type { T } from "./t";
interface I {
  m(): void;
}
type A = Repo;
enum E { X, Y }
class S extends B {
  run(x: number): Repo { return new Repo(); }
}
declare function ambient(): void;
"""

TSX_SOURCE = """import { A } from "./a";
export function App(): JSX.Element {
  const C = () => <span />;
  return <div>{helper(1)}</div>;
}
"""

GO_SOURCE = """package main

import "fmt"

type Repo struct {
\tX int
}

func (r *Repo) Save(x int) error {
\treturn nil
}

func Plain(a int) int {
\treturn a
}

func main() {
\tfmt.Println(Plain(1))
}
"""

JAVA_SOURCE = """package a.b;

import java.util.List;

public class Repo extends Base implements Runnable {
  private List<String> items;

  public Repo(int x) { helper(x); }

  public void save(int x) { helper(x); }

  public static void main(String[] args) { new Repo(1); }
}

interface I {
  void m();
}
"""

KOTLIN_SOURCE = """import kotlin.math.abs

class Repo(val x: Int) : Base() {
    fun save(y: Int): Int { return abs(y) }
}

fun plain(a: Int): Int = a
"""

RUBY_SOURCE = """require "json"

module Util
  def self.build
    1
  end
end

class Repo
  def save(x)
    helper(x)
  end
end
"""

RUST_SOURCE = """use std::collections::HashMap;

struct Repo {
    x: i32,
}

impl Repo {
    fn save(&self, y: i32) -> i32 {
        helper(y)
    }
}

trait T {
    fn signal(&self);
}

fn plain(a: i32) -> i32 {
    println!("{}", a);
    a
}
"""

C_SOURCE = """#include <stdio.h>

struct Repo {
    int x;
};

enum Color { RED, GREEN };

int plain(int a) {
    return helper(a);
}
"""

CPP_SOURCE = """#include <string>

template <typename T>
T plain(T a) {
    return a;
}

class Repo {
 public:
    int save(int x) { return helper(x); }
};

int Repo::load(int x) { return helper(x); }
"""

CSHARP_SOURCE = """using System;

namespace N {
public class Repo : Base {
    public int Save(int x) => Helper(x);
    public Repo() {}
    ~Repo() {}
    public void Run() {
        int Local() { return 1; }
        helper();
    }
}
}
"""

PHP_SOURCE = """<?php
namespace App;

interface Speaker { public function speak(): string; }

class Repo extends Base implements Speaker {
    public function save(int $x): int { return helper($x); }
}

function plain($a) { return $a; }

$r = new Repo();
$r->save(1);
Repo::make(2);
"""

SWIFT_SOURCE = """import Foundation

protocol P {
    func m()
}

class C: B {
    init(x: Int) {}
    deinit {}
    func save(x: Int) -> Int { return helper(x) }
}
"""

SCALA_SOURCE = """class Repo extends Base {
  def save(x: Int): Int = helper(x)
}

object Main {
  def run(): Unit = {}
}

trait T {
  def m(): Int
}
"""

ELIXIR_SOURCE = """defmodule A do
  def save(x) do
    helper(x)
  end

  defp small(y), do: y

  defmacro big(z), do: z
end
"""

LUA_SOURCE = """local M = {}

function M.save(x)
  return helper(x)
end

local function plain(a)
  return a
end
"""

PERL_SOURCE = """use strict;

sub save {
  my ($self, $x) = @_;
  return helper($x);
}

sub plain { return 1; }
"""

DART_SOURCE = """class Repo extends Base {
  int save(int x) { return helper(x); }
  int m();
}

abstract class A {
  int f();
}

int plain(int a) => a;
"""

BASH_SOURCE = """#!/usr/bin/env bash
function save {
  helper "$1"
}

plain() {
  echo hi
}
"""

SQL_SOURCE = """CREATE TABLE users (id INT);
CREATE VIEW active AS SELECT 1;
CREATE FUNCTION add(a INT, b INT) RETURNS INT AS $$ SELECT a; $$ LANGUAGE SQL;
SELECT add(1) FROM users;
"""

CSS_SOURCE = """@keyframes spin { from { top: 0; } }
.card { width: calc(100% - 2px); }
"""

HCL_SOURCE = """variable "region" { default = "us" }
resource "aws_instance" "web" {
  ami = file("x.txt")
}
"""

MAKE_SOURCE = """CC = gcc

all: build
\t$(CC) -o out main.c

build:
\techo build
"""

ZIG_SOURCE = """const std = @import("std");

pub fn plain(a: i32) i32 {
    return a;
}
"""

HASKELL_SOURCE = """module Main where

import Data.List

f :: Int -> Int
f x = g x

data Repo = Repo { x :: Int }

class C a where
  m :: a -> Int
  m _ = 1
"""

OCAML_SOURCE = """let plain a = helper a

type t = { x : int }

module M = struct
  let inner = 1
end

class c = object
  method m = 1
end
"""

OCAML_INTERFACE_SOURCE = """val plain : int -> int

type t = { x : int }
"""


def _shape(path: str, source: str) -> list[tuple[str, str, int, int, str]]:
    parsed = _parser.parse(path, source)

    return [(s.kind, s.qualified_name, s.start_line, s.end_line, s.signature) for s in parsed.symbols]


def _names(path: str, source: str) -> list[str]:
    return [symbol.qualified_name for symbol in _parser.parse(path, source).symbols]


# --------------------------------------------------------------------------- #
# supports()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("extension", sorted(EXTENSION_TO_GRAMMAR))
def test_supports_every_extension_in_the_map(extension: str) -> None:
    assert _parser.supports(f"src/module{extension}") is True


@pytest.mark.parametrize("filename", sorted(FILENAME_TO_GRAMMAR))
def test_supports_extensionless_filenames(filename: str) -> None:
    assert _parser.supports(filename) is True


@pytest.mark.parametrize("path", ["notes.txt", "README", "src/", "", "archive.tar.gz", "Makefile.am"])
def test_supports_is_false_for_anything_else(path: str) -> None:
    assert _parser.supports(path) is False


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #


def test_python_symbols_carry_exact_kinds_names_lines_and_signatures() -> None:
    assert _shape("module.py", PYTHON_SOURCE) == [
        ("class", "Repo", 9, 15, "class Repo(Base):"),
        ("method", "Repo.save", 10, 11, "def save(self, x: int) -> None:"),
        ("method", "Repo.value", 13, 15, "@property\n    def value(self):"),
        ("function", "plain", 17, 18, "def plain(a):"),
        ("function", "outer", 20, 22, "def outer():"),
        ("function", "inner", 21, 22, "def inner():"),
    ]


def test_python_method_body_is_the_whole_method_and_the_signature_is_not() -> None:
    symbol = _parser.parse("module.py", PYTHON_SOURCE).find("Repo.save")

    assert symbol is not None
    assert symbol.body == "def save(self, x: int) -> None:\n        self.x = helper(x)"
    assert symbol.line_count == 2
    assert "helper(x)" not in symbol.signature


def test_python_decorators_belong_to_the_symbol_they_decorate() -> None:
    parsed = _parser.parse("module.py", PYTHON_SOURCE)

    # `@property` sits above the method, so the symbol starts on the decorator line.
    assert parsed.find("Repo.value").start_line == 13  # type: ignore[union-attr]
    assert parsed.find("Repo").body.startswith("class Repo(Base):")  # type: ignore[union-attr]


def test_python_a_nested_function_is_a_function_and_not_a_method_of_the_outer_one() -> None:
    kinds = {symbol.name: symbol.kind for symbol in _parser.parse("module.py", PYTHON_SOURCE).symbols}

    assert kinds == {
        "Repo": "class",
        "save": "method",
        "value": "method",
        "plain": "function",
        "outer": "function",
        "inner": "function",
    }


def test_python_imports_cover_absolute_relative_aliased_and_wildcard_forms() -> None:
    assert _parser.parse("module.py", PYTHON_SOURCE).imports == (
        ImportDTO(module="os", names=(), relative=False),
        ImportDTO(module="x.y", names=("z",), relative=False),
        ImportDTO(module="a.b", names=("c", "d"), relative=False),
        ImportDTO(module="a.b", names=("renamed",), relative=False),
        ImportDTO(module=".", names=("q",), relative=True),
        ImportDTO(module=".rel", names=("e",), relative=True),
        ImportDTO(module="a", names=("*",), relative=False),
    )


def test_python_referenced_names_include_calls_and_annotations() -> None:
    referenced = _parser.parse("module.py", PYTHON_SOURCE).referenced_names

    # `Repo().load(1)` yields both the constructor it calls and the last segment of
    # the attribute chain, and the annotation contributes the type it names.
    assert referenced == frozenset({"Repo", "helper", "load", "int"})


# --------------------------------------------------------------------------- #
# JavaScript / TypeScript
# --------------------------------------------------------------------------- #


def test_javascript_symbols_and_their_lines() -> None:
    assert _shape("app.js", JAVASCRIPT_SOURCE) == [
        ("function", "f", 4, 4, "(x) =>"),
        ("class", "C", 5, 7, "class C"),
        ("method", "C.m", 6, 6, "m()"),
        ("function", "g", 8, 8, "function g()"),
    ]


def test_javascript_imports_cover_named_default_namespace_and_side_effect_forms() -> None:
    assert _parser.parse("app.js", JAVASCRIPT_SOURCE).imports == (
        ImportDTO(module="./m.js", names=("d", "b"), relative=True),
        ImportDTO(module="pkg", names=("ns",), relative=False),
        ImportDTO(module="./side-effect.js", names=(), relative=True),
        ImportDTO(module="./cjs.js", names=(), relative=True),
        ImportDTO(module="./dyn.js", names=(), relative=True),
    )


def test_javascript_an_anonymous_function_is_not_a_named_symbol() -> None:
    # `(function () {})()` has no name to report, and inventing one would be worse
    # than skipping it.
    assert "f" in _names("app.js", JAVASCRIPT_SOURCE)
    assert len(_names("app.js", JAVASCRIPT_SOURCE)) == 4


def test_javascript_referenced_names_include_called_functions() -> None:
    referenced = _parser.parse("app.js", JAVASCRIPT_SOURCE).referenced_names

    assert {"helper", "a", "require"} <= referenced


def test_typescript_symbols_include_interfaces_type_aliases_and_enums() -> None:
    assert _shape("app.ts", TYPESCRIPT_SOURCE) == [
        ("class", "I", 2, 4, "interface I"),
        ("method", "I.m", 3, 3, "m(): void"),
        ("class", "A", 5, 5, "type A = Repo;"),
        ("class", "E", 6, 6, "enum E"),
        ("class", "S", 7, 9, "class S extends B"),
        ("method", "S.run", 8, 8, "run(x: number): Repo"),
        ("function", "ambient", 10, 10, "function ambient(): void;"),
    ]


def test_typescript_imports_and_type_references() -> None:
    parsed = _parser.parse("app.ts", TYPESCRIPT_SOURCE)

    assert parsed.imports == (ImportDTO(module="./t", names=("T",), relative=True),)
    # `type A = Repo` and `new Repo()` both mention the type the review should follow.
    assert "Repo" in parsed.referenced_names


def test_tsx_uses_the_tsx_grammar() -> None:
    parsed = _parser.parse("view.tsx", TSX_SOURCE)

    assert parsed.language == "tsx"
    assert _shape("view.tsx", TSX_SOURCE) == [
        ("function", "App", 2, 5, "function App(): JSX.Element"),
        ("function", "C", 3, 3, "() =>"),
    ]
    assert parsed.imports == (ImportDTO(module="./a", names=("A",), relative=True),)


def test_a_ts_file_and_a_tsx_file_are_parsed_by_different_grammars() -> None:
    assert _parser.parse("view.ts", TSX_SOURCE).language == "typescript"
    assert _parser.parse("view.tsx", TSX_SOURCE).language == "tsx"


# --------------------------------------------------------------------------- #
# Compiled languages
# --------------------------------------------------------------------------- #


def test_go_symbols_methods_and_structs() -> None:
    assert _shape("main.go", GO_SOURCE) == [
        ("class", "Repo", 5, 7, "Repo struct {"),
        ("method", "Repo.Save", 9, 11, "func (r *Repo) Save(x int) error"),
        ("function", "Plain", 13, 15, "func Plain(a int) int"),
        ("function", "main", 17, 19, "func main()"),
    ]


def test_go_a_receiver_makes_a_function_a_method() -> None:
    parsed = _parser.parse("main.go", GO_SOURCE)

    assert parsed.find("Repo.Save").kind == "method"  # type: ignore[union-attr]
    assert parsed.find("Plain").kind == "function"  # type: ignore[union-attr]
    assert {"Plain", "Println"} <= parsed.referenced_names


def test_java_symbols_constructors_and_abstract_methods() -> None:
    assert _shape("Main.java", JAVA_SOURCE) == [
        ("class", "Repo", 5, 13, "public class Repo extends Base implements Runnable"),
        ("method", "Repo.Repo", 8, 8, "public Repo(int x)"),
        ("method", "Repo.save", 10, 10, "public void save(int x)"),
        ("method", "Repo.main", 12, 12, "public static void main(String[] args)"),
        ("class", "I", 15, 17, "interface I"),
        ("method", "I.m", 16, 16, "void m();"),
    ]


def test_java_references_types_and_called_methods() -> None:
    referenced = _parser.parse("Main.java", JAVA_SOURCE).referenced_names

    assert {"helper", "Repo", "Base", "List", "String"} <= referenced


def test_kotlin_symbols_and_calls() -> None:
    parsed = _parser.parse("App.kt", KOTLIN_SOURCE)

    assert _shape("App.kt", KOTLIN_SOURCE) == [
        ("class", "Repo", 3, 5, "class Repo(val x: Int) : Base()"),
        ("method", "Repo.save", 4, 4, "fun save(y: Int): Int"),
        ("function", "plain", 7, 7, "fun plain(a: Int): Int"),
    ]
    assert "abs" in parsed.referenced_names


def test_c_symbols_and_declarator_name_lookup() -> None:
    assert _shape("lib.c", C_SOURCE) == [
        ("class", "Repo", 3, 5, "struct Repo"),
        ("class", "Color", 7, 7, "enum Color"),
        ("function", "plain", 9, 11, "int plain(int a)"),
    ]
    assert "helper" in _parser.parse("lib.c", C_SOURCE).referenced_names


def test_cpp_template_wrapper_is_emitted_once_and_spans_the_template() -> None:
    assert _shape("lib.cpp", CPP_SOURCE) == [
        ("function", "plain", 3, 6, "template <typename T>\nT plain(T a)"),
        ("class", "Repo", 8, 11, "class Repo"),
        ("method", "Repo.save", 10, 10, "int save(int x)"),
        ("function", "Repo::load", 13, 13, "int Repo::load(int x)"),
    ]


def test_csharp_symbols_classes_constructors_and_local_functions() -> None:
    assert _shape("Program.cs", CSHARP_SOURCE) == [
        ("class", "Repo", 4, 12, "public class Repo : Base"),
        ("method", "Repo.Save", 5, 5, "public int Save(int x)"),
        ("method", "Repo.Repo", 6, 6, "public Repo()"),
        ("method", "Repo.Repo", 7, 7, "~Repo()"),
        ("method", "Repo.Run", 8, 11, "public void Run()"),
        # A local function belongs to the method, not to the class.
        ("function", "Local", 9, 9, "int Local()"),
    ]
    assert {"Helper", "helper"} <= _parser.parse("Program.cs", CSHARP_SOURCE).referenced_names


def test_rust_impl_blocks_name_their_methods_without_becoming_symbols() -> None:
    assert _shape("lib.rs", RUST_SOURCE) == [
        ("class", "Repo", 3, 5, "struct Repo"),
        ("method", "Repo.save", 8, 10, "fn save(&self, y: i32) -> i32"),
        ("class", "T", 13, 15, "trait T"),
        ("method", "T.signal", 14, 14, "fn signal(&self);"),
        ("function", "plain", 17, 20, "fn plain(a: i32) -> i32"),
    ]
    assert {"helper", "println"} <= _parser.parse("lib.rs", RUST_SOURCE).referenced_names


def test_swift_initialisers_and_protocol_methods() -> None:
    parsed = _parser.parse("App.swift", SWIFT_SOURCE)

    assert _shape("App.swift", SWIFT_SOURCE) == [
        ("class", "P", 3, 5, "protocol P"),
        ("method", "P.m", 4, 4, "func m()"),
        ("class", "C", 7, 11, "class C: B"),
        # Swift spells constructors without a name, so the parser supplies one.
        ("method", "C.init", 8, 8, "init(x: Int)"),
        ("method", "C.deinit", 9, 9, "deinit"),
        ("method", "C.save", 10, 10, "func save(x: Int) -> Int"),
    ]
    assert "helper" in parsed.referenced_names


def test_scala_symbols_for_classes_objects_traits_and_bodyless_methods() -> None:
    assert _shape("App.scala", SCALA_SOURCE) == [
        ("class", "Repo", 1, 3, "class Repo extends Base"),
        ("method", "Repo.save", 2, 2, "def save(x: Int): Int ="),
        ("class", "Main", 5, 7, "object Main"),
        ("method", "Main.run", 6, 6, "def run(): Unit ="),
        ("class", "T", 9, 11, "trait T"),
    ]
    assert "helper" in _parser.parse("App.scala", SCALA_SOURCE).referenced_names


# --------------------------------------------------------------------------- #
# Scripting languages
# --------------------------------------------------------------------------- #


def test_elixir_definitions_are_recognised_through_their_call_target() -> None:
    assert _shape("app.ex", ELIXIR_SOURCE) == [
        ("class", "A", 1, 9, "defmodule A"),
        ("method", "A.save", 2, 4, "def save(x)"),
        ("method", "A.small", 6, 6, "defp small(y), do: y"),
        ("method", "A.big", 8, 8, "defmacro big(z), do: z"),
    ]
    assert "helper" in _parser.parse("app.ex", ELIXIR_SOURCE).referenced_names


def test_lua_functions_keep_their_table_prefix_in_the_name() -> None:
    assert _shape("app.lua", LUA_SOURCE) == [
        ("function", "M.save", 3, 5, "function M.save(x)"),
        ("function", "plain", 7, 9, "local function plain(a)"),
    ]
    assert "helper" in _parser.parse("app.lua", LUA_SOURCE).referenced_names


def test_perl_subroutines() -> None:
    assert _shape("lib.pm", PERL_SOURCE) == [
        ("function", "save", 3, 6, "sub save"),
        ("function", "plain", 8, 8, "sub plain"),
    ]
    assert "helper" in _parser.parse("lib.pm", PERL_SOURCE).referenced_names


def test_dart_splits_a_declaration_from_its_sibling_body() -> None:
    assert _shape("main.dart", DART_SOURCE) == [
        ("class", "Repo", 1, 4, "class Repo extends Base"),
        ("method", "Repo.save", 2, 2, "int save(int x)"),
        ("method", "Repo.m", 3, 3, "int m()"),
        ("class", "A", 6, 8, "abstract class A"),
        ("method", "A.f", 7, 7, "int f()"),
        ("function", "plain", 10, 10, "int plain(int a)"),
    ]
    # Dart spells a call as an identifier followed by a selector rather than a call
    # node, so it contributes types but no callee names; the table documents that.
    assert "int" in _parser.parse("main.dart", DART_SOURCE).referenced_names


def test_bash_functions_in_both_spellings() -> None:
    assert _shape("run.sh", BASH_SOURCE) == [
        ("function", "save", 2, 4, "function save"),
        ("function", "plain", 6, 8, "plain()"),
    ]
    assert {"helper", "echo"} <= _parser.parse("run.sh", BASH_SOURCE).referenced_names


# --------------------------------------------------------------------------- #
# Query, markup and configuration languages
# --------------------------------------------------------------------------- #


def test_sql_create_statements() -> None:
    parsed = _parser.parse("query.sql", SQL_SOURCE)

    assert _names("query.sql", SQL_SOURCE) == ["users", "active", "add"]
    assert [symbol.kind for symbol in parsed.symbols] == ["class", "class", "function"]
    assert "add" in parsed.referenced_names


def test_css_rule_sets_and_keyframes() -> None:
    assert _shape("style.css", CSS_SOURCE) == [
        ("class", "spin", 1, 1, "@keyframes spin { from { top: 0; } }"),
        ("class", "card", 2, 2, ".card"),
    ]
    assert "calc" in _parser.parse("style.css", CSS_SOURCE).referenced_names


def test_hcl_blocks_are_named_by_their_labels() -> None:
    parsed = _parser.parse("infra.tf", HCL_SOURCE)

    assert _names("infra.tf", HCL_SOURCE) == ["variable.region", "resource.aws_instance.web"]
    assert parsed.imports == ()
    assert "file" in parsed.referenced_names


def test_makefile_rules() -> None:
    assert _shape("Makefile", MAKE_SOURCE) == [
        ("class", "all", 3, 4, "all: build"),
        ("class", "build", 6, 7, "build:"),
    ]


def test_zig_functions() -> None:
    assert _shape("main.zig", ZIG_SOURCE) == [("function", "plain", 3, 5, "pub fn plain(a: i32) i32")]


def test_haskell_bindings_are_not_confused_with_function_types() -> None:
    parsed = _parser.parse("Main.hs", HASKELL_SOURCE)

    # `f :: Int -> Int` uses the same `function` node as the definition, so only the
    # definition (the one with a body) may become a symbol.
    assert _shape("Main.hs", HASKELL_SOURCE) == [
        ("function", "f", 6, 6, "f x"),
        ("class", "Repo", 8, 8, "data Repo = Repo { x :: Int }"),
        ("class", "C", 10, 12, "class C a where"),
        ("method", "C.m", 12, 12, "m _"),
    ]
    assert "g" in parsed.referenced_names


def test_ocaml_values_types_modules_and_classes() -> None:
    assert _shape("lib.ml", OCAML_SOURCE) == [
        ("function", "plain", 1, 1, "let plain a ="),
        ("class", "t", 3, 3, "type t ="),
        ("class", "M", 5, 7, "module M ="),
        ("method", "M.inner", 6, 6, "let inner ="),
        ("class", "c", 9, 11, "class c ="),
        ("method", "c.m", 10, 10, "method m ="),
    ]
    assert "helper" in _parser.parse("lib.ml", OCAML_SOURCE).referenced_names


def test_ocaml_interfaces_use_the_interface_grammar() -> None:
    parsed = _parser.parse("lib.mli", OCAML_INTERFACE_SOURCE)

    assert parsed.language == "ocaml_interface"
    assert _shape("lib.mli", OCAML_INTERFACE_SOURCE) == [
        ("function", "plain", 1, 1, "val plain : int -> int"),
        ("class", "t", 3, 3, "type t ="),
    ]


@pytest.mark.parametrize(
    ("path", "grammar"),
    [
        ("data.yaml", "yaml"),
        ("data.yml", "yaml"),
        ("data.json", "json"),
        ("page.html", "html"),
        ("page.htm", "html"),
        ("Dockerfile", "dockerfile"),
        ("image.dockerfile", "dockerfile"),
    ],
)
def test_declaration_free_languages_are_still_parsed(path: str, grammar: str) -> None:
    parsed = _parser.parse(path, "a: 1\nb: [1, 2]\n")

    assert parsed.language == grammar
    assert parsed.is_parsed is True
    assert parsed.symbols == ()
    assert parsed.imports == ()
    assert parsed.referenced_names == frozenset()


# --------------------------------------------------------------------------- #
# Failure modes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["notes.txt", "README", "src/", "", "archive.tar.gz"])
def test_an_unknown_extension_yields_an_empty_dto(path: str) -> None:
    parsed = _parser.parse(path, "def f():\n    pass\n")

    assert parsed == ParsedFileDTO()
    assert parsed.is_parsed is False
    assert _parser.supports(path) is False


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("broken.py", "def f(:\n    ???\n"),
        ("broken.js", "class {{{{"),
        ("broken.go", "func ("),
        ("broken.java", "public class {"),
        ("broken.rb", "def ;;; end end"),
        ("broken.ex", "defmodule do\n"),
    ],
)
def test_broken_syntax_is_recovered_without_an_exception(path: str, source: str) -> None:
    parsed = _parser.parse(path, source)

    # The grammar recovers what it can; the review only needs "no exception".
    assert parsed.is_parsed is True
    assert isinstance(parsed.symbols, tuple)
    assert isinstance(parsed.imports, tuple)


@pytest.mark.parametrize(
    ("path", "source"),
    [("empty.py", ""), ("blank.py", "\n\n"), ("spaces.py", "   \t\n  \n"), ("empty.go", "")],
)
def test_empty_and_whitespace_only_files(path: str, source: str) -> None:
    parsed = _parser.parse(path, source)

    assert parsed.is_parsed is True
    assert parsed.symbols == ()
    assert parsed.imports == ()
    assert parsed.referenced_names == frozenset()


def test_unreadable_text_does_not_raise() -> None:
    # A lone surrogate cannot be encoded as UTF-8; the parser must still answer.
    parsed = _parser.parse("weird.py", "x = '\ud800'\ndef f():\n    pass\n")

    assert parsed.is_parsed is True


def test_parse_returns_an_empty_dto_when_the_grammar_cannot_load(monkeypatch) -> None:
    monkeypatch.setattr(tree_sitter_parser, "language_for", lambda grammar: None)

    assert _parser.parse("module.py", "def f():\n    pass\n") == ParsedFileDTO()


def test_parse_returns_an_empty_dto_when_the_grammar_raises(monkeypatch) -> None:
    class _BrokenParser:
        def __init__(self, language: object) -> None:
            self.language = language

        def parse(self, data: bytes) -> object:
            raise RuntimeError("the wheel is broken")

    monkeypatch.setattr(tree_sitter_parser, "Parser", _BrokenParser)

    assert _parser.parse("module.py", "def f():\n    pass\n") == ParsedFileDTO()


def test_each_parse_builds_its_own_parser(monkeypatch) -> None:
    class _RecordingParser:
        instances: list[_RecordingParser] = []

        def __init__(self, language: object) -> None:
            self.language = language
            _RecordingParser.instances.append(self)

        def parse(self, data: bytes) -> object:
            # The real parser, so the recorded calls still produce real trees.
            return Parser(self.language).parse(data)  # type: ignore[arg-type]

    _RecordingParser.instances = []
    monkeypatch.setattr(tree_sitter_parser, "Parser", _RecordingParser)

    assert _parser.parse("module.py", "def f():\n    pass\n").is_parsed is True
    assert _parser.parse("main.go", "package main\n").is_parsed is True
    assert len(_RecordingParser.instances) == 2
    assert _RecordingParser.instances[0] is not _RecordingParser.instances[1]


def test_two_languages_in_a_row_both_parse() -> None:
    python = _parser.parse("module.py", "def f():\n    pass\n")
    go = _parser.parse("main.go", "package main\n\nfunc main() {}\n")

    assert python.language == "python"
    assert go.language == "go"
    assert [symbol.name for symbol in go.symbols] == ["main"]


def test_helpers_tolerate_a_missing_node() -> None:
    assert _text(b"", None) == ""
    assert _callee_name(b"", None) == ""
    assert _owner_name(b"", None) == ""


def test_helpers_return_nothing_when_a_node_carries_no_name() -> None:
    tree = Parser(language_for("python")).parse(b"1")  # type: ignore[arg-type]

    assert _field_name(b"1", tree.root_node) == ""
    assert _owner_name(b"1", tree.root_node) == ""
