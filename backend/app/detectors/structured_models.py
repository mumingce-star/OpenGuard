"""Import-bound static model literals. Parse target text, never execute it."""
from __future__ import annotations

import ast
import json
import re
import tomllib

# These are SDK call contracts, not model, file or benchmark allowlists.
_CALLS = {
    'smolagents.InferenceClientModel': ('model', 'model_id', 'huggingface'),
    'smolagents.TransformersModel': ('model', 'model_id', 'huggingface'),
    'litellm.anthropic.messages.acreate': ('model', 'model', 'anthropic'),
    **{f'litellm.google_genai.{name}': ('model', 'model', 'google') for name in (
        'generate_content', 'agenerate_content',
        'generate_content_stream', 'agenerate_content_stream',
    )},
    # Constructors are explicit SDK-client declarations.  They establish a
    # service reference, not a successful remote request or authorization.
    'openai.OpenAI': ('api', 'api', 'openai'),
    'openai.AsyncOpenAI': ('api', 'api', 'openai'),
    'anthropic.Anthropic': ('api', 'api', 'anthropic'),
    'anthropic.AsyncAnthropic': ('api', 'api', 'anthropic'),
    'google.genai.Client': ('api', 'api', 'google'),
    'google.generativeai.GenerativeModel': ('api', 'api', 'google'),
    'cohere.Client': ('api', 'api', 'cohere'),
    'mistralai.Mistral': ('api', 'api', 'mistral'),
    'mistralai.client.Mistral': ('api', 'api', 'mistral'),
}
_CONFIG_KEYS = {
    'model': ('model', 'huggingface'), 'model_id': ('model', 'huggingface'),
    'model_name': ('model', 'huggingface'), 'model_name_or_path': ('model', 'huggingface'),
    'pretrained_model_name_or_path': ('model', 'huggingface'),
    'dataset': ('dataset', 'huggingface'), 'dataset_id': ('dataset', 'huggingface'),
    'dataset_name': ('dataset', 'huggingface'), 'dataset_path': ('dataset', 'huggingface'),
}
_API_ENDPOINTS = {
    'https://api.openai.com/v1': ('api', 'openai'),
    'https://api.anthropic.com': ('api', 'anthropic'),
    'https://generativelanguage.googleapis.com': ('api', 'google'),
    'https://api.cohere.com': ('api', 'cohere'),
    'https://api.mistral.ai': ('api', 'mistral'),
}
_API_CONFIG_KEYS = frozenset({
    'api_base', 'api_url', 'base_url', 'endpoint', 'openai_base_url',
    'anthropic_base_url', 'google_api_base', 'cohere_base_url', 'mistral_base_url',
})
_SIMPLE_YAML = re.compile(r"^[ ]*(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<quote>['\"])(?P<value>[^'\"\\\r\n]+)(?P=quote)\s*$")
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


def _call_contract(imported, attrs):
    qualified = '.'.join([imported, *attrs])
    if qualified in _CALLS:
        return _CALLS[qualified]
    if attrs and attrs[-1] == 'from_pretrained' and (imported == 'transformers' or imported.startswith('transformers.')):
        return 'model', 'pretrained_model_name_or_path', 'huggingface'
    if qualified == 'datasets.load_dataset':
        return 'dataset', 'path', 'huggingface'
    return None


def _literal_call_argument(node, parameter):
    values = [kw.value for kw in node.keywords if kw.arg == parameter]
    if len(values) == 1 and not any(kw.arg is None for kw in node.keywords):
        return values[0]
    if not values and not any(kw.arg is None for kw in node.keywords) and node.args:
        return node.args[0]
    return None


def _valid_name(provider, name):
    return (bool(name) and len(name) <= 200 and not any(c.isspace() or ord(c) < 32 for c in name)
            and (provider != 'huggingface' or (_HF_NAME.fullmatch(name) is not None and all(p not in {'.', '..'} for p in name.split('/')))))


def _python_asset_references(locator, text):
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
            rule = _call_contract(imported, path[1])
            if rule is None:
                continue
            asset_type, parameter, provider = rule
            if asset_type == 'api':
                # An SDK constructor has no resource-name argument.  Keep the
                # provider as its stable identity and never expose constructor
                # arguments (which may contain credentials) as evidence.
                yield asset_type, provider, provider, node.lineno + offset, (node.end_lineno or node.lineno) + offset, ('example_reference' if locator.endswith('.md') else 'actual_call')
                continue
            values = [kw.value for kw in node.keywords if kw.arg == parameter]
            # A literal keyword mapping is a structured configuration, not a
            # runtime value.  Accept it only when it contributes exactly one
            # literal target key; any duplicate, dynamic unpacking or mixed
            # direct/unpacked spelling remains intentionally unresolved.
            unpacked = [kw.value for kw in node.keywords if kw.arg is None]
            if unpacked:
                if values or len(unpacked) != 1 or not isinstance(unpacked[0], ast.Dict):
                    continue
                literal_items = [
                    value for key, value in zip(unpacked[0].keys, unpacked[0].values)
                    if isinstance(key, ast.Constant) and key.value == parameter
                ]
                if (len(literal_items) != 1
                        or len(unpacked[0].keys) != 1
                        or any(key is None or not isinstance(key, ast.Constant) or key.value != parameter
                               for key in unpacked[0].keys)):
                    continue
                values = literal_items
            if len(values) != 1 and not values:
                literal = _literal_call_argument(node, parameter)
                values = [literal] if literal is not None else []
            if len(values) != 1:
                continue
            literal = values[0]
            if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
                continue
            name = literal.value
            if not _valid_name(provider, name):
                continue
            yield asset_type, provider, name, literal.lineno + offset, (literal.end_lineno or literal.lineno) + offset, ('example_reference' if locator.endswith('.md') else 'actual_call')


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _config_asset_references(locator, text):
    if locator.endswith('.json'):
        try:
            value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
        except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError, MemoryError):
            return
    elif locator.endswith('.toml'):
        try:
            value = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, UnicodeError, ValueError, RecursionError, MemoryError):
            return
    elif locator.endswith(('.yaml', '.yml')):
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = _SIMPLE_YAML.fullmatch(line)
            if match and match.group('key') in _CONFIG_KEYS:
                asset_type, provider = _CONFIG_KEYS[match.group('key')]
                name = match.group('value')
                if _valid_name(provider, name):
                    yield asset_type, provider, name, line_number, line_number, 'explicit_config_candidate'
            elif match and match.group('key') in _API_CONFIG_KEYS:
                api = _API_ENDPOINTS.get(match.group('value').rstrip('/'))
                if api:
                    asset_type, provider = api
                    yield asset_type, provider, provider, line_number, line_number, 'explicit_config_candidate'
        return
    else:
        return
    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in _CONFIG_KEYS and isinstance(child, str):
                    asset_type, provider = _CONFIG_KEYS[key]
                    if _valid_name(provider, child):
                        yield asset_type, provider, child
                elif key in _API_CONFIG_KEYS and isinstance(child, str):
                    api = _API_ENDPOINTS.get(child.rstrip('/'))
                    if api:
                        asset_type, provider = api
                        yield asset_type, provider, provider
                yield from visit(child)
        elif isinstance(item, list):
            for child in item:
                yield from visit(child)
    for asset_type, provider, name in visit(value):
        expression = re.compile(r"(?:['\\\"]?" + re.escape(name) + r"['\\\"]?)")
        line = next((index for index, source in enumerate(text.splitlines(), start=1) if expression.search(source)), 1)
        yield asset_type, provider, name, line, line, 'explicit_config_candidate'


def structured_asset_references(locator, text):
    yield from _python_asset_references(locator, text)
    yield from _config_asset_references(locator, text)


def structured_model_references(locator, text):
    """Backward-compatible model-only iterator for existing callers."""
    for asset_type, provider, name, start_line, end_line, _origin in structured_asset_references(locator, text):
        if asset_type == 'model':
            yield provider, name, start_line, end_line
