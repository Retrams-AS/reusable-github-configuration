# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml==6.0.2", "tree-sitter-language-pack==1.22.1"]
# ///
"""Prototype symbol-level floor: which changed lines the model may judge, per the spec
services/ci-workflows/initiatives/2026-10-16-fast-track-symbol-floor in Documentation."""
import fnmatch
import re
import subprocess
from pathlib import PurePosixPath

from tree_sitter_language_pack import get_parser

LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".vue": "vue"}
DEFS = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "method_definition", "class_declaration",
                   "arrow_function", "function_expression", "function"},
}
DEFS["typescript"] = DEFS["javascript"] | {"interface_declaration"}


def sh(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _text(node, src):
    return src[node.start_byte:node.end_byte].decode(errors="replace")


def _name(node, src):
    n = node.child_by_field_name("name")
    if n is not None:
        return _text(n, src)
    # An anonymous function takes the name it is bound to: `const f = () =>`, `{ f() {} }`,
    # `{ f: () => }`, or the call it is passed to (`router.beforeEach(() => ...)` is `beforeEach`).
    p = node.parent
    if p is not None and p.type == "variable_declarator":
        return _text(p.child_by_field_name("name"), src)
    if p is not None and p.type == "pair":
        return _text(p.child_by_field_name("key"), src).strip("'\"")
    if p is not None and p.type == "arguments" and p.parent is not None:
        fn = p.parent.child_by_field_name("function")
        if fn is not None:
            return _text(fn, src).split(".")[-1]
    return "<anonymous>"


def _calls(node, src):
    out, stack = set(), [node]
    while stack:
        n = stack.pop()
        if n.type in ("call", "call_expression"):
            fn = n.child_by_field_name("function")
            if fn is not None:
                out.add(re.split(r"[.\s]", _text(fn, src))[-1])
        stack.extend(n.children)
    return out


def symbols(source: str, lang: str, line_offset=0):
    """Every function, method and class: (first line, last line, qualified name, calls), 1-based."""
    src = source.encode()
    tree = get_parser(lang).parse(src)
    if tree.root_node.has_error:
        raise ValueError("parse error")
    defs = DEFS[lang]
    out = []

    def walk(node, prefix):
        for c in node.children:
            if c.type in defs:
                name = f"{prefix}{_name(c, src)}"
                # A Python decorator belongs to what it decorates.
                start = c.parent if c.parent is not None and c.parent.type == "decorated_definition" else c
                out.append((start.start_point[0] + 1 + line_offset, c.end_point[0] + 1 + line_offset,
                            name, _calls(c, src)))
                walk(c, f"{name}.")
            else:
                walk(c, prefix)

    walk(tree.root_node, "")
    return out


def file_symbols(path: str, source: str):
    lang = LANG.get(PurePosixPath(path).suffix)
    if lang is None:
        raise ValueError("unsupported language")
    if lang != "vue":
        return symbols(source, lang)
    # Vue: parse each <script> block as TS or JS at its own line offset.
    out = []
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", source, re.S):
        sub = "typescript" if re.search(r'lang=["\']ts', m.group(1)) else "javascript"
        offset = source.count("\n", 0, m.start(2))
        out += symbols(m.group(2), sub, offset)
    return out


def changed_lines(base, head, path, cwd=None):
    """(old lines, new lines) changed in path between two commits, from a zero-context diff."""
    old, new = set(), set()
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
                         sh("git", "diff", "-U0", "--no-renames", base, head, "--", path, cwd=cwd), re.M):
        a, b, c, d = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
        old |= set(range(a, a + b))
        new |= set(range(c, c + d))
        if b == 0:  # a pure insertion lands inside whatever surrounds line a on the old side
            old.add(a)
    return old, new


def _match_symbol(path, name, patterns):
    for pat in patterns:
        pglob, _, sglob = pat.partition("::")
        if PurePosixPath(path).full_match(pglob) and (
                fnmatch.fnmatchcase(name, sglob or "*") or fnmatch.fnmatchcase(name.split(".")[-1], sglob or "*")):
            return True
    return False


def held(path, base, head, risk_map, cwd=None):
    """Why this changed file is held at the floor, or [] when the model may judge all of it."""
    p = PurePosixPath(path)
    if p.parts[:1] == (".github",):
        return ["under .github"]
    if not any(p.full_match(g) for g in risk_map.get("fast", [])):
        return ["not on the fast lane"]
    if any(p.full_match(g) for g in risk_map.get("critical", [])):
        return ["critical file"]
    csym, ccall = risk_map.get("critical-symbols", []), set(risk_map.get("critical-calls", []))
    if not csym and not ccall:
        return []
    if PurePosixPath(path).suffix not in LANG:
        # No parser: today's file-level rule, unless the map names symbols in this file.
        named = any(p.full_match(pat.partition("::")[0]) for pat in csym)
        return ["whole file (no parser, symbols named)"] if named else []
    old, new = changed_lines(base, head, path, cwd)
    reasons = []
    for rev, lines in ((base, old), (head, new)):
        if not lines:
            continue
        try:
            src = sh("git", "show", f"{rev}:{path}", cwd=cwd)
        except subprocess.CalledProcessError:
            continue  # added or deleted: the other side has it
        try:
            syms = file_symbols(path, src)
        except ValueError as e:
            return [f"whole file ({e})"]  # a parse error fails closed
        for line in lines:
            inside = [s for s in syms if s[0] <= line <= s[1]]
            if not inside:
                continue  # module level
            first, last, name, calls = max(inside, key=lambda s: s[0])
            if _match_symbol(path, name, csym):
                reasons.append(f"{name}: critical symbol")
            elif calls & ccall:
                reasons.append(f"{name}: calls {sorted(calls & ccall)}")
    return sorted(set(reasons))
