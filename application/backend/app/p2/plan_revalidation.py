"""Narrow read-only proof for a new schema version after an actual v2 rejection."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

from .action_plan import (ANALYSIS_PROTOCOL, PROMPT_VERSION, PlanSemanticError,
                          prepare_plan_payload, plan_schema, validate_plan)
from .contract import canonical, digest, strict_json


def _read(root, identity, suffix):
    if type(identity) is not str or not re.fullmatch(r'plan-[0-9a-f]{32}', identity):
        raise ValueError('prior plan audit identity')
    root = Path(root)
    info = root.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('prior plan audit directory')
    fd = os.open(root/(identity+'-'+suffix+'.json'), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid()
                or before.st_mode & 0o077 or before.st_size > 98304):
            raise ValueError('prior plan audit file')
        raw = os.read(fd, 98305)
        after = os.fstat(fd)
        fields = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if fields(before) != fields(after) or len(raw) != before.st_size:
            raise ValueError('prior plan audit changed')
    finally:
        os.close(fd)
    value = strict_json(raw)
    if canonical(value) != raw:
        raise ValueError('prior plan audit bytes')
    return value


def prior_v2_issues(preview, payload, *, audit_root):
    """No success, transport failure or different context can become retry-eligible."""
    if (PROMPT_VERSION != 'p2-bound-action-plan/9' or preview.get('analysis_protocol') != ANALYSIS_PROTOCOL
            or preview.get('model', {}).get('prompt_version') != 'p2-bound-action-plan/8'
            or preview.get('status') != 'failed' or preview.get('error_code') != 'p2_ai_output_rejected'
            or type(preview.get('model_calls')) is not int or not 1 <= preview['model_calls'] <= 2
            or preview.get('plan') is not None or any(preview.get(k) != [] for k in ('actions', 'clauses', 'changes'))):
        raise ValueError('prior plan not eligible')
    base = prepare_plan_payload({**payload, 'analysis_protocol': ANALYSIS_PROTOCOL})
    if preview.get('plan_input_sha256') != digest(base) or preview.get('usage') != payload['usage']:
        raise ValueError('prior plan context conflict')
    attempts = preview.get('attempts')
    if not isinstance(attempts, list) or len(attempts) != preview['model_calls']:
        raise ValueError('prior plan attempts')
    issues = []
    expected_request = base
    for index, attempt in enumerate(attempts, 1):
        if (not isinstance(attempt, dict) or attempt.get('number') != index or type(attempt.get('number')) is not int
                or attempt.get('state') != 'semantic_rejected' or type(attempt.get('model_calls')) is not int
                or attempt['model_calls'] != 1 or attempt.get('prompt_version') != 'p2-bound-action-plan/8'):
            raise ValueError('prior plan attempt state')
        raw, parsed = attempt.get('raw_output'), attempt.get('parsed_plan')
        if (not isinstance(raw, str) or not isinstance(parsed, dict) or strict_json(raw) != parsed
                or hashlib.sha256(raw.encode()).hexdigest() != attempt.get('raw_output_sha256')
                or digest(expected_request) != attempt.get('input_sha256')):
            raise ValueError('prior plan raw identity')
        intent = _read(audit_root, attempt['audit_id'], 'intent')
        if (intent.get('request') != expected_request or intent.get('request', {}).get('plan_context') != base['plan_context']
                or intent.get('attempt', {}).get('input_sha256') != attempt['input_sha256']
                or _read(audit_root, attempt['audit_id'], 'result') != attempt):
            raise ValueError('prior plan audit binding')
        old = attempt.get('validation')
        if (not isinstance(old, dict) or old.get('status') != 'failed' or old.get('code') != 'plan_change_kind'
                or old.get('recoverable') is not True or old.get('details', {}).get('expected') != 'usage_change'
                or old.get('parent_output_sha256') != attempt['raw_output_sha256']
                or old.get('parent_input_sha256') != attempt['input_sha256']):
            raise ValueError('prior plan rejection evidence')
        try:
            validate_plan(raw, expected_request)
        except PlanSemanticError as exc:
            if exc.code != 'plan_change_kind' or exc.path != old.get('path') or exc.details.get('expected') != 'usage_change':
                raise ValueError('prior plan rejection changed') from None
            issues.append({'attempt': index, 'code': exc.code, 'path': exc.path, 'details': exc.details,
                'raw_output_sha256': attempt['raw_output_sha256'], 'input_sha256': attempt['input_sha256'],
                'context_sha256': base['plan_context']['context_sha256']})
        else:
            raise ValueError('prior plan no current rejection')
        feedback = {k: old[k] for k in ('code', 'path', 'details', 'parent_output_sha256', 'parent_input_sha256')}
        expected_request = prepare_plan_payload({**base, 'plan_feedback': feedback})
    return issues, {'schema_sha256': digest(plan_schema(base)), 'plan_input_sha256': digest(base),
                    'context_sha256': base['plan_context']['context_sha256']}
