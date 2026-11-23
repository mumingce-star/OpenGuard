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


def _v4_metrics(provider):
    values = getattr(provider, 'last_metrics', {})
    return {key: values[key] for key in ('prompt_eval_count', 'eval_count', 'total_duration')
            if key in values and type(values[key]) is int and values[key] >= 0}


def run_v4_plan(provider, payload, *, audit_root, max_model_calls=2):
    from .v4_action_plan import ANALYSIS_PROTOCOL, PROMPT_VERSION, plan_prompt, validate_plan

    if type(max_model_calls) is not int or max_model_calls not in {1, 2}:
        raise ValueError('invalid explicit v4 plan call limit')
    context = payload['context']
    required = sorted(row['action_kind'] for row in context['action_catalog'] if row['required'])
    plan, attempts = None, []
    clauses, actions, changes = [], [], []
    issues = []
    request = payload
    error = None
    if len(required) > 4:
        error = 'p2_ai_v4_required_action_overflow'
    elif not context['action_catalog']:
        error = 'p2_ai_v4_no_actions'
    elif len(canonical(payload)) > 24000:
        error = 'p2_ai_input_too_large'
    if error is not None:
        issues.append({'code': error, 'recoverable': False, 'path': 'context'})
    else:
        for number in range(1, max_model_calls + 1):
            identity = 'plan-v4-' + uuid4().hex
            started = time.monotonic()
            attempt = {'number': number, 'audit_id': identity, 'state': 'intent',
                       'input_sha256': digest(request), 'prompt_version': PROMPT_VERSION,
                       'prompt_sha256': hashlib.sha256(plan_prompt(request).encode()).hexdigest(),
                       'raw_output_sha256': None, 'model_calls': 0, 'metrics': {}}
            try:
                _artifact(audit_root, identity, 'intent', {'attempt': attempt, 'request': request})
            except (OSError, ValueError):
                error = 'p2_ai_audit_unavailable'
                issues.append({'code': error, 'recoverable': False, 'path': 'audit'})
                break

            raw = None
            correction = False
            try:
                raw = provider.generate(request)
                if not isinstance(raw, str) or len(raw.encode('utf-8')) > 98304:
                    raise ValueError('invalid structured response')
                attempt['raw_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
                parsed = strict_json(raw)
                clauses, actions, changes = validate_plan(raw, request)
                plan, error = parsed, None
                attempt['state'] = 'succeeded'
            except PlanSemanticError as exc:
                error = exc.code
                issues.append({'code': exc.code, 'path': exc.path, 'recoverable': exc.recoverable is True})
                attempt['state'] = 'semantic_rejected'
                correction = (number == 1 and max_model_calls == 2 and exc.recoverable is True
                              and attempt['raw_output_sha256'] is not None)
            except BudgetError as exc:
                allowed = {'p2_ai_busy','p2_ai_budget_invalid','p2_ai_budget_exhausted',
                           'p2_ai_rate_limited','p2_ai_input_too_large','p2_ai_protocol_disabled'}
                error = str(exc) if str(exc) in allowed else 'p2_ai_unavailable'
                attempt['state'] = 'budget_refused'
                issues.append({'code': error, 'recoverable': False, 'path': 'budget'})
            except (ValueError, TypeError, KeyError):
                error = 'p2_ai_v4_invalid_output'
                attempt['state'] = 'malformed_or_invalid_output'
                issues.append({'code': error, 'recoverable': False, 'path': 'response'})
            except Exception as exc:
                error = 'p2_ai_model_timeout' if isinstance(exc, TimeoutError) else 'p2_ai_model_unavailable'
                attempt['state'] = 'transport_or_runtime_failure'
                issues.append({'code': error, 'recoverable': False, 'path': 'transport'})

            calls = getattr(provider, 'model_calls', 0)
            attempt['model_calls'] = 1 if type(calls) is int and calls == 1 else 0
            attempt['metrics'] = {'elapsed_ms': round((time.monotonic()-started)*1000), **_v4_metrics(provider)}
            try:
                _artifact(audit_root, identity, 'result',
                          {**attempt, 'raw_output': raw if isinstance(raw, str) and attempt['raw_output_sha256'] else None,
                           'error_code': error})
            except (OSError, ValueError):
                plan, correction, error = None, False, 'p2_ai_audit_unavailable'
                attempt['state'] = 'audit_failed'
                issues.append({'code': error, 'recoverable': False, 'path': 'audit'})
            attempts.append(attempt)
            if error is None or not correction:
                break
            request = {**payload, 'plan_feedback': {'code': error, 'required_action_kinds': required,
                                                   'parent_output_sha256': attempt['raw_output_sha256']}}
            if len(canonical(request)) > 24000:
                error = 'p2_ai_input_too_large'
                issues.append({'code': error, 'recoverable': False, 'path': 'context'})
                break

    succeeded = plan is not None and error is None
    details = {'protocol': ANALYSIS_PROTOCOL, 'status': 'validated' if succeeded else 'failed',
               'human_review_required': True, 'issues': issues, 'corrective_attempt_used': len(attempts) == 2,
               'attempt_count': len(attempts), 'model_call_limit': max_model_calls}
    return {'analysis_protocol': ANALYSIS_PROTOCOL, 'prompt_version': PROMPT_VERSION,
            'context': context, 'context_sha256': payload['context_sha256'],
            'material_claims_view_id': context['material_claims_view_id'],
            'plan_input_sha256': digest(payload), 'display_origin': 'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION',
            'selection_sha256': digest(plan) if succeeded else None, 'plan': plan if succeeded else None,
            'status': 'succeeded' if succeeded else 'failed', 'error_code': error,
            'validation_details': details, 'attempts': attempts,
            'clauses': clauses if succeeded else [], 'actions': actions if succeeded else [],
            'changes': changes if succeeded else [], 'model_calls': sum(row['model_calls'] for row in attempts)}


def validate_saved_v4_plan(value, payload):
    from .v4_action_plan import ANALYSIS_PROTOCOL, PROMPT_VERSION, validate_plan

    context = payload['context']
    if (value['analysis_protocol'] != ANALYSIS_PROTOCOL or value['context'] != context
            or value['context_sha256'] != payload['context_sha256']
            or value['material_claims_view_id'] != context['material_claims_view_id']
            or value['plan_input_sha256'] != digest(payload) or value['input_sha256'] != digest(payload)
            or value['display_origin'] != 'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION'
            or value['formal_effect'] != 'none'
            or value['prompt_version'] != PROMPT_VERSION or value['model']['prompt_version'] != PROMPT_VERSION):
        raise ValueError('saved v4 plan input identity conflict')
    if value['status'] == 'failed':
        if (value['plan'] is not None or value['selection_sha256'] is not None
                or any(value[key] for key in ('clauses','actions','changes'))):
            raise ValueError('failed v4 plan unexpectedly contains a selection')
        return
    if value['status'] != 'succeeded' or value['selection_sha256'] != digest(value['plan']):
        raise ValueError('saved v4 selection identity conflict')
    clauses, actions, changes = validate_plan(canonical(value['plan']).decode(), payload)
    if (value['clauses'], value['actions'], value['changes']) != (clauses, actions, changes):
        raise ValueError('saved v4 rendered output conflict')
