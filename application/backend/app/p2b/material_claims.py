"""Bounded text observations for the first material/claim slice.

No network, model, storage, source trust or legal applicability decision here.
The complete MIT matcher is relocated verbatim from p2.preliminary (legacy API
re-exports it). Permission/condition/warranty text is the existing local rule,
not a newly downloaded SPDX canonical corpus.
"""
from __future__ import annotations
import hashlib
import re

PERMISSION = ('Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:')
CONDITION = 'The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.'
WARRANTY = ('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.')

def complete_mit(raw: bytes) -> bool:
    try:
        text = raw.decode('utf-8', errors='strict').replace('\r\n', '\n').strip()
    except UnicodeError:
        return False
    if '\x00' in text or '\r' in text:
        return False
    paragraphs = re.split(r'\n\s*\n', text)
    if len(paragraphs) != 5 or paragraphs[0] not in {'MIT License', 'The MIT License (MIT)'}:
        return False
    if not all(re.fullmatch(r'Copyright \(c\) [^\x00-\x1f]+', line) for line in paragraphs[1].splitlines()):
        return False
    return [' '.join(p.split()) for p in paragraphs[2:]] == [PERMISSION, CONDITION, WARRANTY]



def _span(raw: bytes, text: str, start: int, end: int, kind: str) -> dict:
    begin = len(text[:start].encode('utf-8'))
    finish = len(text[:end].encode('utf-8'))
    quote = text[start:end]
    return {'kind': kind, 'byte_start': begin, 'byte_end': finish,
            'line_start': text.count('\n', 0, start) + 1,
            'line_end': text.count('\n', 0, max(start, end - 1)) + 1,
            'quote': quote, 'quote_sha256': hashlib.sha256(raw[begin:finish]).hexdigest()}


def parse_claim_material(raw: bytes, filename: str) -> dict:
    """Text profile only. Even MATCHED_MIT never establishes source/usage trust."""
    base = {'parse_state': 'FAILED', 'text_license': 'UNKNOWN',
            'license_version': None, 'reason': 'INVALID_INPUT', 'spans': []}
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
        return {**base, 'reason': 'MATERIAL_SIZE_LIMIT'}
    if not isinstance(filename, str) or not re.fullmatch(r'(?:LICENSE|LICENCE|NOTICE)(?:\.(?:txt|md|rst))?', filename, re.I):
        return {**base, 'reason': 'UNSUPPORTED_FILENAME'}
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        return {**base, 'reason': 'INVALID_UTF8'}
    if '\x00' in text or not text.strip():
        return {**base, 'reason': 'BINARY_OR_EMPTY'}
    if filename.split('.')[0].upper() == 'NOTICE':
        return {**base, 'parse_state': 'NOTICE_OBSERVED', 'reason': 'NOTICE_NOT_A_GRANT',
                'spans': [_span(raw, text, 0, len(text), 'notice')]}
    if not complete_mit(raw):
        return {**base, 'parse_state': 'UNSUPPORTED', 'reason': 'FULL_TEXT_PROFILE_NOT_MATCHED'}
    groups = []
    pos, begin = 0, None
    for line in text.splitlines(keepends=True):
        if line.strip():
            if begin is None:
                begin = pos
        elif begin is not None:
            groups.append((begin, pos)); begin = None
        pos += len(line)
    if begin is not None:
        groups.append((begin, len(text)))
    if len(groups) != 5:
        return {**base, 'reason': 'SPAN_MAPPING_FAILED'}
    kinds = ['license_identifier', 'copyright', 'permission', 'condition', 'warranty']
    return {**base, 'parse_state': 'MATCHED_MIT', 'text_license': 'MIT',
            'reason': 'COMPLETE_EXISTING_MIT_PROFILE',
            'spans': [_span(raw, text, a, b, kind) for (a, b), kind in zip(groups, kinds)]}
