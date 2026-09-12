"""Import-bound static model literals. Parse target text, never execute it."""
from __future__ import annotations

import ast
import re

# These are SDK call contracts, not model, file or benchmark allowlists.
_CALLS = {
    'smolagents.InferenceClientModel': ('model_id', 'huggingface'),
    'smolagents.TransformersModel': ('model_id', 'huggingface'),
    'litellm.anthropic.messages.acreate': ('model', 'anthropic'),
    **{f'litellm.google_genai.{name}': ('model', 'google') for name in (
        'generate_content', 'agenerate_content',
        'generate_content_stream', 'agenerate_content_stream',
    )},
}
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_HF_NAME = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')


def _units(locator, text):
    if locator.endswith('.py'):
        yield text, 0
    elif locator.endswith('.md'):
        opening = None
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            match = _FENCE.match(line.rstrip('\r\n'))
            if opening is None:
                if match:
                    fence, info = match.groups()
                    tokens = info.split()
                    opening = (fence, index, bool(tokens and tokens[0] in {'python', 'py', 'python3'}))
            elif match:
                fence, start, supported = opening
                marker, rest = match.groups()
                if marker[0] == fence[0] and len(marker) >= len(fence) and not rest.strip():
                    if supported:
                        yield ''.join(lines[start + 1:index]), start + 1
                    opening = None


def _path(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return node.id, list(reversed(parts))
    return None


def _bindings(tree):
    """Only unambiguous top-level imports; any shadowing rejects that root.

    Deliberately conservative across scopes: no interprocedural binding inference.
    """
    bindings = {}
    invalid = set()
    top_imports = {id(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == '*':
                    return {}
                local = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                if id(node) not in top_imports or (isinstance(node, ast.ImportFrom) and node.level):
                    invalid.add(local)
                    continue
                qualified = (alias.name if alias.asname else local) if isinstance(node, ast.Import) else f'{node.module}.{alias.name}'
                if local in bindings:
                    invalid.add(local)
                bindings[local] = (qualified, node.lineno)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            invalid.add(node.id)
        elif isinstance(node, ast.arg):
            invalid.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            invalid.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            invalid.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            invalid.update(node.names)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            path = _path(node)
            if path:
                invalid.add(path[0])
        elif isinstance(node, ast.MatchAs) and node.name:
            invalid.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            invalid.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            invalid.add(node.rest)
    return {name: value for name, value in bindings.items() if name not in invalid}


def structured_model_references(locator, text):
    for source, offset in _units(locator, text):
        try:
            tree = ast.parse(source)
            bindings = _bindings(tree)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            path = _path(node.func)
            if path is None or path[0] not in bindings:
                continue
            imported, import_line = bindings[path[0]]
            if node.lineno <= import_line:
                continue
            rule = _CALLS.get('.'.join([imported, *path[1]]))
            if rule is None:
                continue
            parameter, provider = rule
            values = [kw.value for kw in node.keywords if kw.arg == parameter]
            if len(values) != 1:
                continue
            literal = values[0]
            if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
                continue
            name = literal.value
            if not name or len(name) > 200 or any(c.isspace() or ord(c) < 32 for c in name):
                continue
            if provider == 'huggingface' and (_HF_NAME.fullmatch(name) is None or any(p in {'.', '..'} for p in name.split('/'))):
                continue
            yield provider, name, literal.lineno + offset, (literal.end_lineno or literal.lineno) + offset
