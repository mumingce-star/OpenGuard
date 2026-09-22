"""A06-only immutable document validation; never reads live sources."""
from datetime import datetime
import hashlib
import json
import re


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def utc(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z',value):
        raise ValueError('report_timestamp_invalid')
    datetime.fromisoformat(value.replace('Z','+00:00'))


def strict_snapshot(value):
    if not isinstance(value,dict):raise ValueError('report_structure_invalid')
    utc(value['created_at']);utc(value['provenance']['generated_at'])
    binding=value['binding'];provenance=value['provenance']
    refs=[binding['scan_ref'],*provenance['source_refs']]
    for ref in refs:
        if ref.get('registry_revision') is not None and (type(ref['registry_revision']) is not int or ref['registry_revision']<0):
            raise ValueError('report_integer_invalid')
    for ref in [binding['assessment_ref'],*provenance['assessment_refs'],*binding['task_refs']]:
        if type(ref['version']) is not int or ref['version']<1:raise ValueError('report_integer_invalid')
    for artifact in value['artifacts']:
        if type(artifact['size_bytes']) is not int or artifact['size_bytes']<0:raise ValueError('report_integer_invalid')
    return value


def strict_json(payload):
    def pairs(items):
        result={}
        for key,val in items:
            if key in result:raise ValueError('duplicate_json_key')
            result[key]=val
        return result
    def constant(_):raise ValueError('non_finite_json')
    try:
        value=json.loads(payload.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
        # Reject overflow floats (e.g. 1e999) as well as named NaN/Infinity.
        canonical(value)
        return value
    except (RecursionError,UnicodeError,OverflowError) as error:
        raise ValueError('report_json_invalid') from error


def explicit_identity(scan_id,assessment_id,task_refs,notice_refs,algorithm_refs):
    return {'scan_id':scan_id,'assessment_id':assessment_id,
            'task_refs':sorted(task_refs,key=lambda x:(x['task_id'],x['version'])),
            'notice_refs':sorted(notice_refs,key=lambda x:(x['draft_id'],x['content_hash'])),
            'algorithm_refs':sorted(algorithm_refs,key=lambda x:(x['kind'],x['version'],x['content_hash']))}


def binding_identity(binding):
    return explicit_identity(binding['scan_ref']['scan_id'],binding['assessment_ref']['assessment_id'],
                             binding['task_refs'],binding['notice_refs'],binding['algorithm_refs'])


def validate_document(snapshot,payload):
    document=strict_json(payload)
    common={k:v for k,v in snapshot.items() if k not in {'content_hash','artifacts','sections'}}
    if not isinstance(document,dict) or set(document)!=set(common)|{'sections'}:
        raise ValueError('report_document_structure')
    if canonical({k:document[k] for k in common})!=canonical(common):raise ValueError('report_document_binding')
    rows=document['sections'];descriptors=snapshot['sections']
    if not isinstance(rows,list) or len(rows)!=len(descriptors) or not rows:raise ValueError('report_sections_invalid')
    base=(f"/api/v1/scans/{snapshot['binding']['scan_ref']['scan_id']}/assessments/"
          f"{snapshot['binding']['assessment_ref']['assessment_id']}/report-v2/{snapshot['snapshot_id']}")
    for index,(row,desc) in enumerate(zip(rows,descriptors)):
        if not isinstance(row,dict) or set(row)!=set(desc)|{'content'}:raise ValueError('report_section_missing')
        if canonical({k:row[k] for k in desc})!=canonical(desc):raise ValueError('report_section_mismatch')
        if desc['snapshot_ref']!=f'{base}?format=json#/sections/{index}/content':raise ValueError('report_section_pointer')
        if not isinstance(row['content'],dict):raise ValueError('report_section_content')
        if hashlib.sha256(canonical(row['content'])).hexdigest()!=desc['content_hash']:raise ValueError('report_section_hash')
    validate_full_sections(snapshot,rows)
    for item in snapshot['artifacts']:
        if item['href']!=base+'?format='+item['format']:raise ValueError('report_artifact_scope')


def validate_full_sections(snapshot, rows):
    """Require full versioned model contents, never reconstruct omitted details."""
    from app.domain.models import ScanRun
    from app.assessment.models import Assessment
    from .models import P1RemediationTask, P1ResourceGraphView
    by={}
    for row in rows:
        by.setdefault(row['authority'],[]).append(row)
    for authority in ('scan_facts','formal_assessment','workflow','ai_explanation'):
        if len(by.get(authority,[]))!=1:raise ValueError('report_full_sections_missing')
    def complete(model, raw):
        parsed=model.model_validate(raw).model_dump(mode='json')
        if canonical(parsed)!=canonical(raw):raise ValueError('report_content_incomplete')
        return parsed
    scan=complete(ScanRun,by['scan_facts'][0]['content'])
    assessment=complete(Assessment,by['formal_assessment'][0]['content'])
    binding=snapshot['binding']
    if scan['id']!=binding['scan_ref']['scan_id'] or assessment['id']!=binding['assessment_ref']['assessment_id']:
        raise ValueError('report_content_identity')
    scan_ref=binding['scan_ref'];assessment_ref=binding['assessment_ref']
    if hashlib.sha256(canonical(scan)).hexdigest()!=scan_ref['facts_hash']:
        raise ValueError('report_scan_hash_mismatch')
    for key,actual in {'revision':scan['project']['revision'],'input_hash':scan['provenance']['input_digest']['value'],
                      'status':scan['status'],'inventory_hash':scan['provenance']['inventory_digest']['value'] if scan['provenance']['inventory_digest'] else None}.items():
        if scan_ref[key]!=actual:raise ValueError('report_scan_binding')
    for key in ('version','scan_id','facts_hash','usage_hash','rule_version','formal'):
        if canonical(assessment_ref[key])!=canonical(assessment[key]):raise ValueError('report_assessment_binding')
    if snapshot['provenance']['source_refs']!=[scan_ref] or snapshot['provenance']['assessment_refs']!=[assessment_ref]:
        raise ValueError('report_provenance_binding')
    for authority,version,ids in [('scan_facts',scan['contract_version'],[scan['id']]),
                                 ('formal_assessment',assessment['schema_version'],[assessment['id']]),
                                 ('workflow','1.0',[r['task_id'] for r in binding['task_refs']]),
                                 ('ai_explanation',assessment['schema_version'],[assessment['id']])]:
        row=by[authority][0]
        if row['schema_version']!=version or row['source_ids']!=ids:raise ValueError('report_section_source')
    workflow=by['workflow'][0]['content']
    if set(workflow)!={'tasks','task_refs'} or workflow['task_refs']!=binding['task_refs']:
        raise ValueError('report_workflow_invalid')
    tasks=[complete(P1RemediationTask,task) for task in workflow['tasks']]
    if [{'task_id':task['task_id'],'version':task['version']} for task in tasks]!=binding['task_refs']:
        raise ValueError('report_task_content_missing')
    ai=by['ai_explanation'][0]['content']
    expected=dict(assessment_id=assessment['id'],assessment_version=assessment['version'],
        ai_status=assessment['ai_status'],ai_summary=assessment['ai_summary'],ai_evidence_ids=assessment['ai_evidence_ids'])
    if canonical(ai)!=canonical(expected):raise ValueError('report_ai_content_mismatch')
    observations=by.get('observation',[])
    notices=binding['notice_refs']
    if len(observations)!=len(binding['algorithm_refs'])+len(notices):raise ValueError('report_observation_missing')
    notice_rows=[row for row in observations if 'draft_id' in row['content']]
    graph_rows=[row for row in observations if 'draft_id' not in row['content']]
    if len(notice_rows)!=len(notices) or len(graph_rows)!=len(binding['algorithm_refs']):
        raise ValueError('report_observation_binding')
    from .report_v2_notice import validate_notice_content, validate_notice_binding
    refs={r['draft_id']:r for r in notices}
    if len(refs)!=len(notices):raise ValueError('report_notice_duplicate')
    seen=set()
    for row in notice_rows:
        draft=row['content'];did=draft['draft_id']
        if did not in refs or did in seen:raise ValueError('report_notice_binding')
        seen.add(did)
        validate_notice_content(draft)
        validate_notice_binding(draft, refs[did], scan_ref, assessment_ref, scan)
        if row['source_ids']!=[did] or row['schema_version']!=draft['schema_version']:
            raise ValueError('report_notice_section')
    for row,reference in zip(graph_rows,binding['algorithm_refs']):
        from .report_v2_graph import graph_content_hash
        graph=complete(P1ResourceGraphView,row['content'])
        if (reference['kind']!='graph' or reference['version']!=graph['provenance']['algorithm_version']
                or reference['content_hash']!=graph_content_hash(graph) or graph['scan_ref']!=scan_ref
                or row['source_ids']!=[graph['view_id']] or row['schema_version']!=graph['schema_version']):
            raise ValueError('report_graph_binding')
