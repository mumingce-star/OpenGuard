"""Bounded plan validation: one initial generation and at most one reasoned correction.

Every returned model string remains immutable in a TASK-private attempt artifact.
Transport failures, malformed JSON, unknown shapes and ambiguous outcomes never retry.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
import time
from uuid import uuid4

from app.ai.p2_analysis import BudgetError
from .contract import canonical, digest, strict_json
from .action_plan import (ANALYSIS_PROTOCOL, PROMPT_VERSION, PlanSemanticError,
                          prepare_plan_payload, plan_prompt, validate_plan)


def enabled():
    value = os.environ.get('OPENGUARD_P2_ACTION_PLAN', '0')
    if value not in {'0', '1'}:
        raise ValueError('invalid action plan configuration')
    return value == '1'


def _artifact(root, identity, suffix, value):
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('invalid action plan audit directory')
    raw = canonical(value)
    fd = os.open(root / (identity + '-' + suffix + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(raw); output.flush(); os.fsync(output.fileno())
    return hashlib.sha256(raw).hexdigest()


def run_plan(provider, payload, *, audit_root, max_model_calls=2):
    """Each generate call independently uses the existing durable global budget."""
    if type(max_model_calls) is not int or max_model_calls not in {1, 2}:
        raise ValueError('invalid explicit action plan call limit')
    base = prepare_plan_payload({**payload, 'analysis_protocol': ANALYSIS_PROTOCOL})
    attempts, clauses, actions, changes = [], [], [], []
    plan = None
    details = {'protocol': ANALYSIS_PROTOCOL, 'status': 'failed', 'human_review_required': True}
    request = deepcopy(base)
    status, error = 'failed', 'p2_ai_output_rejected'
    for number in range(1, max_model_calls + 1):
        identity = 'plan-' + uuid4().hex
        started = time.monotonic()
        attempt = {'number': number, 'audit_id': identity, 'state': 'intent',
            'input_sha256': digest(request), 'prompt_sha256': hashlib.sha256(plan_prompt(request).encode()).hexdigest(),
            'prompt_version': PROMPT_VERSION, 'correction_of_sha256': request.get('plan_feedback', {}).get('parent_output_sha256'),
            'raw_output': None, 'raw_output_sha256': None, 'parsed_plan': None, 'model_calls': 0,
            'validation': None, 'metrics': {}}
        _artifact(audit_root, identity, 'intent', {'attempt': attempt, 'request': request})
        corrective = False
        try:
            raw = provider.generate(request)
            attempt['raw_output'] = raw
            attempt['raw_output_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            parsed = strict_json(raw)
            if not isinstance(parsed, dict):
                raise ValueError('plan top level invalid')
            attempt['parsed_plan'] = parsed
            clauses, actions, changes, details = validate_plan(raw, request)
            plan = parsed
            attempt['validation'] = deepcopy(details)
            attempt['state'] = 'succeeded'
            status, error = 'succeeded', None
        except PlanSemanticError as exc:
            feedback = {'code': exc.code, 'path': exc.path, 'details': exc.details,
                'parent_output_sha256': attempt['raw_output_sha256'], 'parent_input_sha256': attempt['input_sha256']}
            attempt['validation'] = {**feedback, 'status': 'failed', 'recoverable': bool(exc.recoverable)}
            attempt['state'] = 'semantic_rejected'
            details = {'protocol': ANALYSIS_PROTOCOL, 'status': 'failed', 'issues': [deepcopy(attempt['validation'])],
                       'human_review_required': True}
            corrective = max_model_calls == 2 and number == 1 and exc.recoverable is True and isinstance(attempt['parsed_plan'], dict)
            if corrective:
                # Feedback is program-owned typed evidence, never a modified source fact.
                request = prepare_plan_payload({**deepcopy(base), 'plan_feedback': feedback})
        except BudgetError as exc:
            error = str(exc) if str(exc) in {'p2_ai_busy', 'p2_ai_budget_invalid', 'p2_ai_budget_exhausted', 'p2_ai_rate_limited', 'p2_ai_input_too_large', 'p2_ai_protocol_disabled'} else 'p2_ai_unavailable'
            attempt['state'] = 'budget_refused'
            attempt['validation'] = {'status': 'not_run', 'code': error}
        except (ValueError, TypeError, KeyError):
            attempt['state'] = 'malformed_or_invalid_output'
            attempt['validation'] = {'status': 'failed', 'code': 'plan_malformed_or_invalid_output', 'recoverable': False}
        except Exception:
            error = 'p2_ai_model_unavailable'
            attempt['state'] = 'transport_or_runtime_failure'
            attempt['validation'] = {'status': 'not_established', 'code': error, 'recoverable': False}
        finally:
            attempt['model_calls'] = getattr(provider, 'model_calls', 0)
            attempt['metrics'] = {'elapsed_ms': round((time.monotonic()-started)*1000),
                                  **getattr(provider, 'last_metrics', {})}
            _artifact(audit_root, identity, 'result', attempt)
            attempts.append(attempt)
        if status == 'succeeded' or not corrective:
            break
    details = {**details, 'corrective_attempt_used': len(attempts) == 2, 'attempt_count': len(attempts), 'model_call_limit': max_model_calls}
    return {'analysis_protocol': ANALYSIS_PROTOCOL, 'status': status, 'error_code': error,
        'plan': plan, 'validation_details': details, 'attempts': attempts,
        'clauses': clauses if status == 'succeeded' else [], 'actions': actions if status == 'succeeded' else [],
        'changes': changes if status == 'succeeded' else [],
        'model_calls': sum(x['model_calls'] for x in attempts), 'plan_input_sha256': digest(base)}


def validate_saved_plan(value, payload):
    """Recheck stored plan against immutable facts; never regenerate or rewrite."""
    if value.get('analysis_protocol') != ANALYSIS_PROTOCOL or value.get('status') != 'succeeded':
        return
    enriched = prepare_plan_payload({**payload, 'analysis_protocol': ANALYSIS_PROTOCOL})
    if value.get('plan_input_sha256') != digest(enriched):
        raise ValueError('saved plan input identity conflict')
    clauses, actions, changes, details = validate_plan(canonical(value['plan']).decode('utf-8'), enriched)
    candidate = payload.get('source_candidate_inputs') is True
    expected_clauses = [{('source_candidate_id' if k == 'material_id' else k): v for k, v in c.items()} for c in clauses] if candidate else clauses
    expected_actions = [{('source_candidate_ids' if k == 'source_material_ids' else k): v for k, v in a.items()} for a in actions] if candidate else actions
    if value.get('clauses') != expected_clauses or value.get('actions') != expected_actions or value.get('changes') != changes:
        raise ValueError('saved plan rendered output conflict')
    stored = value.get('validation_details', {})
    if any(stored.get(k) != v for k, v in details.items()):
        raise ValueError('saved plan validation conflict')
