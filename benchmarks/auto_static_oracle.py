"""Independent, deliberately narrow oracle for an automated static-reference bench.

This module does not import the product detector or its rule tables.  A label
means that a source literal satisfies this module's published syntax contract;
it does not mean that the resource was used or licensed.
"""

from __future__ import annotations

import ast
from bisect import bisect_right
import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from urllib.parse import urlsplit

ORACLE_VERSION = "automated-static-oracle/5"
_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_URL = re.compile(r"https://[^\s\"'`<>()[\]{}]+")
_ENV_KEYS = {
    "OPENAI_API_KEY": "openai", "ANTHROPIC_API_KEY": "anthropic",
    "GOOGLE_API_KEY": "google", "GEMINI_API_KEY": "google",
}
_API_ENDPOINTS = {
    "https://api.openai.com/v1": "openai",
    "https://api.anthropic.com": "anthropic",
    "https://generativelanguage.googleapis.com": "google",
}
_SDK_MODULES = {
    "openai": ("OpenAI", "openai"),
    "@anthropic-ai/sdk": ("Anthropic", "anthropic"),
    "@google/genai": ("GoogleGenAI", "google"),
    "@google/generative-ai": ("GoogleGenerativeAI", "google"),
}
_MODEL_KEYS = {"model", "model_id", "model_name", "model_name_or_path", "pretrained_model_name_or_path"}
_DATASET_KEYS = {"dataset", "dataset_id", "dataset_name", "dataset_path"}
_API_KEYS = {"api_base", "api_url", "base_url", "endpoint", "openai_base_url", "anthropic_base_url", "google_api_base"}
_YAML_LITERAL = re.compile(r"^\s*([A-Za-z_][\w-]*)\s*:\s*(['\"])([^'\"\\\r\n]+)\2\s*$")
_IMPORT = re.compile(r"^\s*import\s+(?:(\w+)\s+from\s+|\{\s*(\w+)(?:\s+as\s+(\w+))?\s*\}\s+from\s+)['\"]([^'\"]+)['\"]\s*;?\s*$")


def supported(locator: str) -> bool:
    name = locator.rsplit("/", 1)[-1]
    return name == ".env" or name.startswith(".env.") or locator.endswith(
        (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".json", ".toml", ".yaml", ".yml")
    )


def _reference_url(raw: str) -> tuple[str, str, str] | None:
    try:
        parsed = urlsplit(raw.rstrip(".,;"))
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return None
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if host == "huggingface.co":
        if parts[0] == "datasets" and len(parts) >= 3:
            kind, name, tail = "dataset", "/".join(parts[1:3]), parts[3:]
        elif len(parts) >= 2:
            kind, name, tail = "model", "/".join(parts[:2]), parts[2:]
            if parts[0] in {"datasets", "spaces", "docs", "models", "api", "blog", "login", "settings",
                            "papers", "organizations", "collections", "join", "logout", "pricing",
                            "terms-of-service", "privacy", "tasks", "learn", "inference"}:
                return None
        else:
            return None
        if not _NAME.fullmatch(name) or (tail and (len(tail) < 3 or tail[0] not in {"blob", "resolve"})):
            return None
        return kind, "huggingface", name
    if host == "modelscope.cn" and len(parts) == 3 and parts[0] in {"models", "datasets"}:
        name = "/".join(parts[1:])
        if _NAME.fullmatch(name):
            return ("model" if parts[0] == "models" else "dataset"), "modelscope", name
    return None


def _mask_js(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Blank JS comments/strings and retain complete ordinary literals."""
    out = list(text)
    literals: list[tuple[str, int]] = []
    state = "code"
    literal_start = -1
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line"
            elif char == "/" and nxt == "*":
                state = "block"
            elif char in "'\"`":
                state = char
                literal_start = index
            else:
                index += 1
                continue
        elif state == "line" and char == "\n":
            state = "code"
            index += 1
            continue
        elif state == "block" and char == "*" and nxt == "/":
            out[index] = out[index + 1] = " "
            index += 2
            state = "code"
            continue
        elif state in "'\"`" and char == "\\":
            out[index] = " "
            if index + 1 < len(text):
                out[index + 1] = "\n" if nxt == "\n" else " "
            index += 2
            continue
        elif state in "'\"`" and char == state:
            if state != "`":
                literals.append((text[literal_start + 1:index], literal_start))
            out[index] = " "
            state = "code"
            index += 1
            continue
        out[index] = "\n" if char == "\n" else " "
        index += 1
    return "".join(out), literals


def oracle_file(locator: str, text: str) -> dict:
    """Return uniquely located labels and a count of undecidable constructs."""
    if not supported(locator):
        return {"labels": [], "unscored_constructs": 0, "eligible_lines": []}
    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_lines = text.splitlines()
    newline_offsets = [offset for offset, char in enumerate(text) if char == "\n"]
    line_at = lambda offset: bisect_right(newline_offsets, offset) + 1
    labels: dict[tuple, dict] = {}
    unscored = 0
    eligible: set[int] = set()

    def add(kind: str, provider: str, name: str, line: int, rule: str) -> None:
        if line < 1 or line > len(source_lines) + 1:
            return
        eligible.add(line)
        key = (locator, line, kind, provider, name)
        source_line = source_lines[line - 1] if line <= len(source_lines) else ""
        labels[key] = {
            "locator": locator, "line": line, "resource_type": kind,
            "provider": provider, "name": name, "oracle_rule": rule,
            "evidence_sha256": file_hash,
            "excerpt_sha256": hashlib.sha256(source_line.encode("utf-8")).hexdigest(),
            "oracle_version": ORACLE_VERSION,
        }

    def urls(value: str, line: int, rule: str, raw_segment: str | None = None) -> None:
        nonlocal unscored
        cursor = 0
        for match in _URL.finditer(value):
            ref = _reference_url(match.group())
            if ref:
                exact_line = line
                if raw_segment is not None:
                    position = raw_segment.find(match.group(), cursor)
                    if position < 0:
                        unscored += 1
                        continue
                    exact_line += raw_segment.count("\n", 0, position)
                    cursor = position + len(match.group())
                add(*ref, exact_line, rule)

    def config(key: str, value: object, line: int) -> None:
        if not isinstance(value, str):
            return
        if key in _MODEL_KEYS and _NAME.fullmatch(value):
            add("model", "huggingface", value, line, "structured_config")
        elif key in _DATASET_KEYS and _NAME.fullmatch(value):
            add("dataset", "huggingface", value, line, "structured_config")
        elif key in _API_KEYS:
            provider = _API_ENDPOINTS.get(value.rstrip("/"))
            if provider:
                add("api", provider, provider, line, "api_endpoint")
        urls(value, line, "structured_url")

    if locator.endswith(".py"):
        source_bytes = [line.encode("utf-8") for line in text.splitlines(keepends=True)]
        def segment(node: ast.Constant) -> str | None:
            if node.end_lineno is None or node.end_col_offset is None:
                return None
            first = node.lineno - 1
            last = node.end_lineno - 1
            if first == last:
                data = source_bytes[first][node.col_offset:node.end_col_offset]
            else:
                data = (source_bytes[first][node.col_offset:] +
                        b"".join(source_bytes[first + 1:last]) +
                        source_bytes[last][:node.end_col_offset])
            return data.decode("utf-8")
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            return {"labels": [], "unscored_constructs": 1, "eligible_lines": []}
        bindings: dict[str, str] = {}
        shadowed: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    bindings[local] = alias.name if alias.asname else local
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                shadowed.add(node.id)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                eligible.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
                raw_segment = segment(node)
                if raw_segment is None:
                    unscored += 1
                else:
                    urls(node.value, node.lineno, "python_literal_url", raw_segment)
            if not isinstance(node, ast.Call):
                continue
            eligible.add(node.lineno)
            parts = []
            target = node.func
            while isinstance(target, ast.Attribute):
                parts.insert(0, target.attr)
                target = target.value
            if not isinstance(target, ast.Name) or target.id in shadowed or target.id not in bindings:
                continue
            qualified = ".".join((bindings[target.id], *parts))
            provider = {
                "openai.OpenAI": "openai", "openai.AsyncOpenAI": "openai",
                "anthropic.Anthropic": "anthropic", "anthropic.AsyncAnthropic": "anthropic",
                "google.genai.Client": "google", "google.generativeai.GenerativeModel": "google",
            }.get(qualified)
            if provider:
                add("api", provider, provider, node.lineno, "python_sdk_call")
                continue
            if qualified == "datasets.load_dataset":
                kind = "dataset"
            elif qualified.endswith(".from_pretrained") and qualified.startswith("transformers."):
                kind = "model"
            else:
                continue
            args = [kw.value for kw in node.keywords if kw.arg in ({"path"} if kind == "dataset" else {"pretrained_model_name_or_path"})]
            if not args and node.args:
                args = [node.args[0]]
            if len(args) == 1 and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str) and _NAME.fullmatch(args[0].value):
                add(kind, "huggingface", args[0].value, args[0].lineno, "python_literal_call")
            else:
                unscored += 1
    elif locator.endswith((".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")):
        masked, string_literals = _mask_js(text)
        imports: dict[str, tuple[str, bool]] = {}
        for match in re.finditer(r"(?m)^\s*import\b[^\r\n]*", masked):
            original = text[match.start():match.end()]
            parsed = _IMPORT.fullmatch(original)
            if parsed:
                default, named, alias, module = parsed.groups()
                expected = _SDK_MODULES.get(module)
                if expected and (default or named) == expected[0]:
                    imports[alias or default or named] = expected[1], bool(alias or named)
        for match in re.finditer(r"\bnew\s+([A-Za-z_$][\w$]*)\s*\(", masked):
            eligible.add(line_at(match.start()))
            binding = imports.get(match.group(1))
            if binding:
                provider, aliased = binding
                add("api", provider, provider, line_at(match.start()), "javascript_sdk_alias" if aliased else "javascript_sdk_call")
        # URLs only in ordinary quoted literals, never comments or templates.
        for literal, offset in string_literals:
            line_number = line_at(offset)
            eligible.add(line_number)
            urls(literal, line_number, "javascript_literal_url")
    elif locator.endswith((".json", ".toml")):
        try:
            if locator.endswith(".json"):
                def unique(pairs: list[tuple[str, object]]) -> dict:
                    value = {}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError("duplicate key")
                        value[key] = item
                    return value
                document = json.loads(text, object_pairs_hook=unique)
            else:
                document = tomllib.loads(text)
        except (ValueError, tomllib.TOMLDecodeError, RecursionError):
            return {"labels": [], "unscored_constructs": 1, "eligible_lines": []}
        def walk(item: object) -> None:
            nonlocal unscored
            if isinstance(item, Mapping):
                for key, value in item.items():
                    if isinstance(value, str):
                        lines = [i for i, line in enumerate(source_lines, 1) if value in line]
                        if len(lines) == 1:
                            eligible.add(lines[0])
                            config(key, value, lines[0])
                        elif key in _MODEL_KEYS | _DATASET_KEYS | _API_KEYS or _URL.search(value):
                            unscored += 1
                    walk(value)
            elif isinstance(item, list):
                for value in item:
                    walk(value)
        walk(document)
    elif locator.endswith((".yaml", ".yml")):
        for line_number, line in enumerate(source_lines, 1):
            match = _YAML_LITERAL.fullmatch(line)
            if match:
                eligible.add(line_number)
                config(match.group(1), match.group(3), line_number)
    else:
        for line_number, line in enumerate(source_lines, 1):
            match = re.fullmatch(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=.*", line)
            if match:
                eligible.add(line_number)
            if match and match.group(1) in _ENV_KEYS:
                provider = _ENV_KEYS[match.group(1)]
                add("api", provider, provider, line_number, "environment_key")
    return {"labels": [labels[key] for key in sorted(labels)], "unscored_constructs": unscored,
            "eligible_lines": sorted(eligible)}


def self_test() -> None:
    """Fail closed before a run if known positives, negatives or mutations drift."""
    cases = [
        ("a.py", 'import openai\nclient = openai.OpenAI()\nurl = "https://huggingface.co/acme/model"\ndata = "https://modelscope.cn/datasets/acme/data"\n# https://example.com/nope\n',
         {("api", "openai", "openai"), ("model", "huggingface", "acme/model"),
          ("dataset", "modelscope", "acme/data")}),
        ("a.json", '{"model": "acme/model", "irrelevant": "openai", "endpoint": "https://api.anthropic.com"}',
         {("model", "huggingface", "acme/model"), ("api", "anthropic", "anthropic")}),
        ("a.ts", 'import OpenAI from "openai";\nconst x = new OpenAI();\nconst y = "new Anthropic()";\n',
         {("api", "openai", "openai")}),
        ("a.toml", 'model = "acme/model"\n', {("model", "huggingface", "acme/model")}),
        ("a.yaml", "dataset: 'acme/data'\n", {("dataset", "huggingface", "acme/data")}),
        ("negative.json", '{"url": "https://example.com/acme/model"}', set()),
        ("invalid-endpoint.json", '{"api_base": "https://api.openai.com/not-v1"}', set()),
        ("paper.py", 'paper = "https://huggingface.co/papers/2010.02502"\n', set()),
        (".env", 'OPENAI_API_KEY=REDACTED\nOTHER_API_KEY=REDACTED\n', {("api", "openai", "openai")}),
    ]
    for locator, source, expected in cases:
        actual = {(item["resource_type"], item["provider"], item["name"]) for item in oracle_file(locator, source)["labels"]}
        if actual != expected:
            raise RuntimeError(f"oracle self-test failed: {locator}")
        mutated = source + "\n# harmless comment\n" if locator.endswith((".py", ".ts")) else source
        second = {(item["resource_type"], item["provider"], item["name"]) for item in oracle_file(locator, mutated)["labels"]}
        if second != expected:
            raise RuntimeError(f"oracle mutation self-test failed: {locator}")
    dynamic = oracle_file("dynamic.py", "import datasets\nname = choose()\ndatasets.load_dataset(name)\n")
    if dynamic["labels"] or dynamic["unscored_constructs"] != 1:
        raise RuntimeError("oracle dynamic-boundary self-test failed")
