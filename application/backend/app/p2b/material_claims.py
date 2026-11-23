"""Bounded license and NOTICE text observations.

The legacy preliminary route re-exports the original strict MIT matcher.
Normalized matches still map every quote to the uploaded bytes.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
from pathlib import Path
import re

PERMISSION = ('Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:')
CONDITION = 'The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.'
WARRANTY = ('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.')

def _legacy_mit(raw: bytes) -> bool:
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


_COPYRIGHT_PREFIX = r'Copyright(?:[ \t]+(?:\([cC]\)|©))?[ \t]+'
_YEARS = r'[0-9]{4}(?:[-–, ]+[0-9]{4})*'
_HOLDER = r'[ \t]+(?P<holder>[^\x00-\x1f\x7f]+)'
_COPYRIGHT = re.compile(_COPYRIGHT_PREFIX + _YEARS + _HOLDER)
# Retain the exact year shape used by the frozen is-number fixture.
_MIT_COPYRIGHT = re.compile(_COPYRIGHT_PREFIX + rf'(?:{_YEARS}|[0-9]{{4}}-present,)' + _HOLDER)
_BSD_COPYRIGHT = re.compile(_COPYRIGHT_PREFIX + _YEARS + ',?' + _HOLDER)
_LICENSE_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\r(?!\n)')


def _license_text(raw: bytes) -> str | None:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
        return None
    try:
        text = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        return None
    return text if text.strip() and not _LICENSE_CONTROLS.search(text) else None


def _paragraphs(text: str) -> list[tuple[int, int]]:
    paragraphs = []
    position = 0
    begin = None
    for line in re.finditer(r'[^\n]*\n|[^\n]+$', text):
        if line[0].strip():
            if begin is None:
                begin = position
        elif begin is not None:
            paragraphs.append((begin, position))
            begin = None
        position = line.end()
    if begin is not None:
        paragraphs.append((begin, len(text)))
    return paragraphs


def _title_and_body(text: str, allowed_titles: set[str]):
    paragraphs = _paragraphs(text)
    if paragraphs:
        start, end = paragraphs[0]
        title = text[start:end].strip().removesuffix(':').rstrip()
        if title in allowed_titles:
            return [('license_identifier', start, end)], paragraphs[1:]
    return [], paragraphs


def _copyright_holders(text: str, pattern: re.Pattern, *, allow_reserved=False) -> list[str]:
    lines = text.strip().split('\n')
    if allow_reserved and lines[-1].strip() == 'All rights reserved.':
        lines.pop()
    matches = [pattern.fullmatch(line.strip()) for line in lines]
    return [match['holder'] for match in matches] if all(matches) else []


def _mit_ranges(text: str):
    spans, body = _title_and_body(text, {'MIT License', 'The MIT License (MIT)'})
    if len(body) != 4:
        return []
    start, end = body[0]
    if not _copyright_holders(text[start:end], _MIT_COPYRIGHT):
        return []
    if [' '.join(text[a:b].split()) for a, b in body[1:]] != [PERMISSION, CONDITION, WARRANTY]:
        return []
    kinds = ('copyright', 'permission', 'condition', 'warranty')
    return spans + [(kind, start, end) for kind, (start, end) in zip(kinds, body)]


def complete_mit(raw: bytes, *, strict_legacy: bool = True) -> bool:
    """Use the historical five-paragraph profile unless v4 explicitly opts in."""
    if strict_legacy:
        return _legacy_mit(raw)
    text = _license_text(raw)
    return text is not None and bool(_mit_ranges(text))


_APACHE2_LICENSE = Path(__file__).resolve().parents[4] / 'LICENSE'
_APACHE2_PROFILE_SHA256 = '283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b'
_APACHE2_APPENDIX = '\n\n   APPENDIX:'
_APACHE2_TERMS = 'TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION'
_APACHE2_ADDITIONAL_TERMS = 'You may add Your own copyright statement to Your modifications and'
_APACHE2_ANCHORS = re.compile(
    rf'^[ \t]*({_APACHE2_TERMS}|[23478]\.|\([a-d]\)|{_APACHE2_ADDITIONAL_TERMS})(?=[ \t]|\r?$)',
    re.MULTILINE,
)


def _normalized_apache2(raw: bytes) -> str:
    return raw.decode('utf-8', errors='strict').replace('\r\n', '\n').strip()


@lru_cache(maxsize=1)
def _canonical_apache2() -> str:
    canonical = _normalized_apache2(_APACHE2_LICENSE.read_bytes())
    if hashlib.sha256(canonical.encode('utf-8')).hexdigest() != _APACHE2_PROFILE_SHA256:
        raise ValueError('canonical_apache2_profile_mismatch')
    return canonical


def _apache2_matches(text: str) -> bool:
    normalized = text.replace('\r\n', '\n').strip()
    try:
        canonical = _canonical_apache2()
    except (OSError, ValueError):
        return False
    core, separator, appendix = canonical.partition(_APACHE2_APPENDIX)
    if not normalized.startswith(core):
        return False
    curly = appendix.replace('brackets "[]"', 'brackets "{}"').replace(
        '[yyyy] [name of copyright owner]', '{yyyy} {name of copyright owner}',
    )
    tail = normalized[len(core):]
    for allowed in (separator + appendix, separator + curly):
        if tail.startswith(allowed):
            tail = tail[len(allowed):]
            break
    return not tail or tail.startswith('\n') and _COPYRIGHT.fullmatch(tail.strip()) is not None


def complete_apache2(raw: bytes) -> bool:
    """Match the full canonical terms and any recognized appendix and copyright footer."""
    text = _license_text(raw)
    return text is not None and _apache2_matches(text)


_ISC_PERMISSION = ('Permission to use, copy, modify, and/or distribute this software for any purpose with or '
                   'without fee is hereby granted,')
_ISC_CONDITION = 'provided that the above copyright notice and this permission notice appear in all copies.'
_ISC_WARRANTY = (
    'THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE '
    'INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE '
    'FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM '
    'LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, '
    'ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.'
)


def _isc_ranges(text: str):
    spans, body = _title_and_body(text, {'ISC License', 'The ISC License'})
    if len(body) != 3:
        return []
    (copyright_start, copyright_end), (grant_start, grant_end), (warranty_start, warranty_end) = body
    if not _copyright_holders(text[copyright_start:copyright_end], _COPYRIGHT):
        return []
    grant = text[grant_start:grant_end]
    if ' '.join(grant.split()) != _ISC_PERMISSION + ' ' + _ISC_CONDITION:
        return []
    if ' '.join(text[warranty_start:warranty_end].split()) != _ISC_WARRANTY:
        return []
    condition_start = grant_start + grant.index('provided')
    permission_end = len(text[:condition_start].rstrip())
    return spans + [('copyright', copyright_start, copyright_end), ('permission', grant_start, permission_end),
                    ('condition', condition_start, grant_end), ('warranty', warranty_start, warranty_end)]


def complete_isc(raw: bytes) -> bool:
    text = _license_text(raw)
    return text is not None and bool(_isc_ranges(text))


_BSD_INTRO = ('Redistribution and use in source and binary forms, with or without modification, are permitted '
              'provided that the following conditions are met:')
_BSD_SOURCE = ('Redistributions of source code must retain the above copyright notice, this list of conditions '
               'and the following disclaimer.')
_BSD_BINARY = ('Redistributions in binary form must reproduce the above copyright notice, this list of conditions '
               'and the following disclaimer in the documentation and/or other materials provided with the distribution.')
_BSD_ENDORSEMENT = re.compile(
    r'Neither the names? of (?P<holder>.{1,160}) nor the names of (?:its|project) contributors '
    r'may be used to endorse or promote products derived from this software without specific prior written permission\.'
)
_BSD_WARRANTY = (
    'THIS SOFTWARE IS PROVIDED BY {provider} "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, '
    'BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE '
    'ARE DISCLAIMED. IN NO EVENT SHALL {liable} BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, '
    'EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS '
    'OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY '
    'OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) '
    'ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.'
)
_BSD_WARRANTIES = {
    _BSD_WARRANTY.format(provider=provider, liable=liable)
    for provider, liable in (
        ('THE COPYRIGHT HOLDERS AND CONTRIBUTORS', 'THE COPYRIGHT HOLDER OR CONTRIBUTORS'),
        ('THE COPYRIGHT HOLDERS AND CONTRIBUTORS', 'THE COPYRIGHT OWNER OR CONTRIBUTORS'),
        ('THE COPYRIGHT HOLDER AND CONTRIBUTORS', 'THE COPYRIGHT HOLDER OR CONTRIBUTORS'),
        ('THE AUTHOR AND CONTRIBUTORS', 'THE AUTHOR OR CONTRIBUTORS'),
    )
}
_BSD_TITLES = {
    2: {'BSD License', 'BSD-2-Clause', 'BSD-2-Clause License', 'BSD 2-Clause License', 'The BSD 2-Clause License',
        'BSD 2-Clause "Simplified" License'},
    3: {'BSD License', 'BSD-3-Clause', 'BSD-3-Clause License', 'BSD 3-Clause License', 'The BSD 3-Clause License',
        'BSD 3-Clause "New" or "Revised" License'},
}
_BSD_ANCHORS = re.compile(
    r'^[ \t]*(?:(?P<bullet>[1-3]\.|\*)(?=[ \t])|(?P<warranty>THIS(?=\s+SOFTWARE\s+IS\s)))',
    re.MULTILINE,
)


def _bsd_endorsement_matches(text: str, holders: list[str]) -> bool:
    match = _BSD_ENDORSEMENT.fullmatch(text)
    if match is None:
        return False
    holder = match['holder'].removeprefix('the ')
    placeholders = {'copyright holder', '<organization>', '<copyright holder>', '[organization]', '[copyright holder]'}
    return holder in placeholders or any(
        holder == name or holder == name.removesuffix(' and contributors') for name in holders
    )


def _bsd_ranges(text: str, count: int):
    spans, body = _title_and_body(text, _BSD_TITLES[count])
    if len(body) < 2:
        return []
    copyright_start, copyright_end = body[0]
    holders = _copyright_holders(text[copyright_start:copyright_end], _BSD_COPYRIGHT, allow_reserved=True)
    if not holders:
        return []
    intro_start = body[1][0]
    anchors = list(_BSD_ANCHORS.finditer(text, intro_start))
    if len(anchors) != count + 1 or anchors[-1]['warranty'] is None:
        return []
    markers = tuple(anchor['bullet'] for anchor in anchors[:-1])
    if markers not in (('*',) * count, tuple(f'{n}.' for n in range(1, count + 1))):
        return []
    if ' '.join(text[intro_start:anchors[0].start()].split()) != _BSD_INTRO:
        return []
    conditions = [' '.join(text[anchor.end():following.start()].split())
                  for anchor, following in zip(anchors, anchors[1:])]
    if conditions[:2] != [_BSD_SOURCE, _BSD_BINARY]:
        return []
    if count == 3 and not _bsd_endorsement_matches(conditions[2], holders):
        return []
    warranty_start = anchors[-1].start()
    if ' '.join(text[warranty_start:].split()) not in _BSD_WARRANTIES:
        return []
    spans += [('copyright', copyright_start, copyright_end),
              ('permission', intro_start, len(text[:anchors[0].start()].rstrip()))]
    spans.extend(('condition', anchor.start(), len(text[:following.start()].rstrip()))
                 for anchor, following in zip(anchors, anchors[1:]))
    return spans + [('warranty', warranty_start, len(text.rstrip()))]


def complete_bsd2(raw: bytes) -> bool:
    text = _license_text(raw)
    return text is not None and bool(_bsd_ranges(text, 2))


def complete_bsd3(raw: bytes) -> bool:
    text = _license_text(raw)
    return text is not None and bool(_bsd_ranges(text, 3))


def _span(raw: bytes, text: str, start: int, end: int, kind: str) -> dict:
    begin = len(text[:start].encode('utf-8'))
    finish = len(text[:end].encode('utf-8'))
    quote = text[start:end]
    return {'kind': kind, 'byte_start': begin, 'byte_end': finish,
            'line_start': text.count('\n', 0, start) + 1,
            'line_end': text.count('\n', 0, max(start, end - 1)) + 1,
            'quote': quote, 'quote_sha256': hashlib.sha256(raw[begin:finish]).hexdigest()}


def _apache2_spans(raw: bytes, text: str) -> list[dict]:
    anchors = {match[1]: match.start() for match in _APACHE2_ANCHORS.finditer(text)}
    identifier_start = len(text) - len(text.lstrip())
    ranges = [
        ('license_identifier', identifier_start, anchors[_APACHE2_TERMS]),
        ('permission', anchors['2.'], anchors['3.']),
        ('permission', anchors['3.'], anchors['4.']),
        ('condition', anchors['(a)'], anchors['(b)']),
        ('condition', anchors['(b)'], anchors['(c)']),
        ('condition', anchors['(c)'], anchors['(d)']),
        ('condition', anchors['(d)'], anchors[_APACHE2_ADDITIONAL_TERMS]),
        ('warranty', anchors['7.'], anchors['8.']),
    ]
    return [_span(raw, text, begin, len(text[:end].rstrip()), kind) for kind, begin, end in ranges]


_COPYLEFT_TOKENS = re.compile(r'[^ \t\r\n\f]+')
_COPYLEFT_CLAUSES = ('license_identifier', 'permission', 'condition', 'warranty')

# SHA-256 of the entire document after folding ASCII whitespace. The verbatim
# inputs, source references and raw digests are in task49-copyleft-licenses.json.
# The ranges are half-open token ranges in that complete, immutable document.
_COPYLEFT_DOCUMENTS = {
    'e8ba82e63ba908724aaee6043943c5a2629b9ebf1af581ea0eea19a713123685': (
        'MPL-2.0', (0, 5), (465, 547), (837, 1309), (1665, 1811),  # title, §2.1, §3, §6
    ),
    '04747bc19d9eb83b5ba43a81275faed327e38230c2fbc5439496736b3d260d2f': (
        'GPL-2.0', (0, 8), (487, 751), (751, 1167), (2287, 2491),  # title, §§0–1, §2, §§11–12
    ),
    '0366f6619935ba5e41cf905e400e53d1a491751f103d3739d9e0aec22e171d92': (
        'GPL-3.0', (0, 9), (1245, 1459), (1683, 1993), (4942, 5033),  # title, §2, §5, §15
    ),
    '749f03a5886beb4d1be889d90679193dc78b32d1530daff64b8296ab5f41e930': (
        'LGPL-2.1', (0, 9), (999, 1375), (1375, 1805), (3826, 4030),  # title, §§0–1, §2, §§15–16
    ),
    '7b3ee35820a089523b4d31482806e1a0c3db035f7ab1856d167d61d89876b480': (
        'LGPL-3.0', (0, 10), (286, 319), (555, 916),  # title, §1, §4
        # The standalone text incorporates GPL-3.0, which contains the warranty.
    ),
    '2cd0fb7883a3b3553dedbb0bad171646d46f51e2642951aae7c59cb5cec86c46': (
        'AGPL-3.0', (0, 10), (1112, 1326), (4511, 4698), (4907, 4998),  # title, §2, §13, §15
    ),
}


def _copyleft_observation(raw: bytes, text: str) -> dict | None:
    tokens = list(_COPYLEFT_TOKENS.finditer(text))
    canonical = ' '.join(token[0] for token in tokens)
    profile = _COPYLEFT_DOCUMENTS.get(hashlib.sha256(canonical.encode('utf-8')).hexdigest())
    if profile is None:
        return None
    family, *ranges = profile
    marker = family.replace('-', '_').replace('.', '_')
    return {
        'parse_state': f'MATCHED_{marker}',
        'text_license': family,
        'reason': f'COMPLETE_CANONICAL_{marker}_PROFILE',
        'spans': [_span(raw, text, tokens[begin].start(), tokens[end - 1].end(), kind)
                  for kind, (begin, end) in zip(_COPYLEFT_CLAUSES, ranges)],
    }


def parse_claim_material(raw: bytes, filename: str) -> dict:
    """Report the matched text profile and exact quote spans."""
    base = {'parse_state': 'FAILED', 'text_license': 'UNKNOWN',
            'license_version': None, 'version_scope': 'RESOURCE_VERSION_NOT_LICENSE_VERSION',
            'reason': 'INVALID_INPUT', 'spans': []}
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
    unsupported = {**base, 'parse_state': 'UNSUPPORTED', 'reason': 'FULL_TEXT_PROFILE_NOT_MATCHED'}
    if _LICENSE_CONTROLS.search(text):
        # Verbatim paginated GNU copies use form feeds. Accept those only after
        # verifying an entire Copyleft document, with other controls rejected.
        if _LICENSE_CONTROLS.search(text.replace('\f', '')):
            return unsupported
        observation = _copyleft_observation(raw, text)
        return {**base, **observation} if observation is not None else unsupported
    if _apache2_matches(text):
        return {**base, 'parse_state': 'MATCHED_APACHE_2_0', 'text_license': 'Apache-2.0',
                'license_version': '2.0', 'version_scope': 'LICENSE_VERSION_AND_RESOURCE_VERSION',
                'reason': 'COMPLETE_CANONICAL_APACHE_2_0_PROFILE', 'spans': _apache2_spans(raw, text)}
    profiles = (
        ('MIT', 'MATCHED_MIT', 'COMPLETE_EXISTING_MIT_PROFILE', _mit_ranges),
        ('ISC', 'MATCHED_ISC', 'COMPLETE_ISC_PROFILE', _isc_ranges),
        ('BSD-2-Clause', 'MATCHED_BSD_2_CLAUSE', 'COMPLETE_BSD_2_CLAUSE_PROFILE', lambda source: _bsd_ranges(source, 2)),
        ('BSD-3-Clause', 'MATCHED_BSD_3_CLAUSE', 'COMPLETE_BSD_3_CLAUSE_PROFILE', lambda source: _bsd_ranges(source, 3)),
    )
    for license_id, state, reason, matcher in profiles:
        matches = matcher(text)
        if matches:
            return {**base, 'parse_state': state, 'text_license': license_id, 'reason': reason,
                    'spans': [_span(raw, text, start, end, kind) for kind, start, end in matches]}
    observation = _copyleft_observation(raw, text)
    if observation is not None:
        return {**base, **observation}
    return unsupported
