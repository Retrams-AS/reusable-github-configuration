"""Names the function around a line, from the tree-sitter AST, so a reviewer sees `onSubmit`
instead of a line number. Parse only; nothing in the PR is run."""
import re
from pathlib import PurePosixPath

LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".vue": "vue"}
DEFS = {
    "python": {"function_definition", "class_definition"},
    "javascript": {"function_declaration", "method_definition", "class_declaration",
                   "arrow_function", "function_expression", "function"},
}
DEFS["typescript"] = DEFS["javascript"] | {"interface_declaration"}


def _text(node, src):
    return src[node.start_byte:node.end_byte].decode(errors="replace")


def _name(node, src):
    n = node.child_by_field_name("name")
    if n is not None:
        return _text(n, src)
    # An anonymous function takes the name it is bound to: a variable, an object key, the
    # variable a call's result is assigned to (`const total = computed(() => ...)`), or a
    # test's title (`it('saves the scan', () => ...)`).
    p = node.parent
    if p is not None and p.type == "variable_declarator":
        return _text(p.child_by_field_name("name"), src)
    if p is not None and p.type == "pair":
        return _text(p.child_by_field_name("key"), src).strip("'\"")
    if p is not None and p.type == "arguments" and p.parent is not None:
        call = p.parent
        if call.parent is not None and call.parent.type == "variable_declarator":
            return _text(call.parent.child_by_field_name("name"), src)
        fn = call.child_by_field_name("function")
        callee = _text(fn, src).split(".")[-1] if fn is not None else "<call>"
        first = p.named_children[0] if p.named_children else None
        if first is not None and first.type in ("string", "template_string") and first is not node:
            return f"{callee}: {_text(first, src).strip(chr(39) + chr(34) + chr(96))}"
        return callee
    return None


def _symbols(source, lang, offset=0, check=False):
    from tree_sitter_language_pack import get_parser

    src = source.encode()
    tree = get_parser(lang).parse(src)
    if check and tree.root_node.has_error:
        raise ValueError("parse error")
    out = []

    def walk(node, prefix):
        for c in node.children:
            if c.type in DEFS[lang]:
                name = _name(c, src)
                full = f"{prefix}{name}" if name else prefix.rstrip(".") or None
                start = c.parent if c.parent is not None and c.parent.type == "decorated_definition" else c
                if full:
                    out.append((start.start_point[0] + 1 + offset, c.end_point[0] + 1 + offset, full))
                walk(c, f"{full}." if full else prefix)
            else:
                walk(c, prefix)

    walk(tree.root_node, "")
    return out


def spans(path, source):
    """Every named function and class as (first line, last line, qualified name), 1-based.

    Raises ValueError for a file with no parser or one that does not parse: callers that decide
    what is critical must treat that file as a whole.
    """
    lang = LANG.get(PurePosixPath(path).suffix)
    if lang is None:
        raise ValueError("no parser for this file type")
    try:
        if lang != "vue":
            return _symbols(source, lang, check=True)
        out = []
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", source, re.S):
            sub = "typescript" if re.search(r'lang=["\']ts', m.group(1)) else "javascript"
            out += _symbols(m.group(2), sub, source.count("\n", 0, m.start(2)), check=True)
        return out
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"parse failed: {type(e).__name__}") from e


def function_at(path, source, line):
    """The innermost named function or class around `line`, or None (module level, or no parser)."""
    try:
        inside = [s for s in spans(path, source) if s[0] <= line <= s[1]]
    except ValueError:
        return None
    return max(inside, key=lambda s: s[0])[2] if inside else None
