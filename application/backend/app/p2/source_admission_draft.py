"""Pure internal draft; no issuer, public DTO, production wiring or persistence.

Controlled pins establish consistency with historical bytes, not authenticity.
Only TEST_ONLY is supported. No file/network/process I/O or license inference.
"""
from __future__ import annotations
import base64
import gzip
import hashlib
import io
import json
import math
import re
import tarfile
import zlib
from datetime import datetime
from ..security.archive_path import normalize_member_path
from ..security.errors import IngestionSecurityError
from ..security.limits import ZipSafetyLimits

VERSION = "openguard-p2-source-admission-draft/1"
USES = ("commercial", "modified", "distributed", "network_service", "training", "redistributed_assets", "source_disclosure")
LIMITS = dict(receipts=262144, metadata=32768, archive=1048576, license=65536, history=2097152)
META_URL = "https://registry.npmjs.org/is-number/7.0.0"
TAR_URL = "https://registry.npmjs.org/is-number/-/is-number-7.0.0.tgz"
BINDING = {"scan_id","assessment_id","assessment_version","registry_revision","project_revision","facts_hash","usage_hash","rule_version","assessment_sha256"}
CLAIM = {"binding","subject","usage","source_receipt_index","prior_result_id","prior_result_revision","source_status","owner_scope_status","source_policy_version","repository_commit"}
STATUSES = {"missing","pending","rejected","conflict","revoked"}

class DraftError(ValueError):
    """Only fixed, code-owned error codes cross this boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def _require(condition, code):
    if not condition:
        raise DraftError(code)

def _sha(b):
    return hashlib.sha256(b).hexdigest()

def _canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False).encode()

def _json(raw):
    def pairs(items):
        out = {}
        for k,v in items:
            _require(k not in out, "DRAFT_JSON_INVALID")
            out[k]=v
        return out
    def constant(_):
        raise DraftError("DRAFT_JSON_INVALID")
    def number(text):
        value = float(text)
        _require(math.isfinite(value), "DRAFT_JSON_INVALID")
        return value
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc,DraftError):
            raise
        raise DraftError("DRAFT_JSON_INVALID") from None

def _id(x, maximum=200):
    return type(x) is str and 0<len(x)<=maximum and re.fullmatch(r"[A-Za-z0-9_.:-]+",x) is not None

def _hex(x, size=64):
    return type(x) is str and re.fullmatch("[0-9a-f]{%d}"%size,x) is not None

def _int(x, minimum=0, maximum=1000000):
    return type(x) is int and minimum<=x<=maximum

def _text(b):
    try:
        t=b.decode("utf-8")
    except UnicodeError:
        raise DraftError("DRAFT_TEXT_INVALID") from None
    _require(bool(t.strip()) and "\0" not in t,"DRAFT_TEXT_INVALID")

def _check_claim(c):
    _require(type(c) is dict and set(c)==CLAIM,"DRAFT_INPUT_INVALID")
    b,s,u=c["binding"],c["subject"],c["usage"]
    _require(type(b) is dict and set(b)==BINDING,"DRAFT_INPUT_INVALID")
    _require(all(_id(b[k],300) for k in ("scan_id","assessment_id","rule_version")) and
             all(_hex(b[k]) for k in ("facts_hash","usage_hash","assessment_sha256")) and
             all(_int(b[k],1) for k in ("assessment_version","registry_revision")) and
             (b["project_revision"] is None or _id(b["project_revision"])),"DRAFT_INPUT_INVALID")
    _require(type(s) is dict and set(s)=={"resource_id","name","version"} and all(_id(s[k]) for k in s),"DRAFT_INPUT_INVALID")
    _require(type(u) is dict and set(u)==set(USES) and all(v is None or type(v) is bool for v in u.values()),"DRAFT_INPUT_INVALID")
    _require(_int(c["source_receipt_index"],0,100) and _int(c["prior_result_revision"],1) and _id(c["prior_result_id"]),"DRAFT_INPUT_INVALID")
    for k in ("source_status","owner_scope_status"):
        _require(type(c[k]) is str and c[k] in STATUSES,"DRAFT_STATUS_INVALID")
    _require(c["source_policy_version"] is None or _id(c["source_policy_version"]),"DRAFT_INPUT_INVALID")
    _require(c["repository_commit"] is None or _hex(c["repository_commit"],40),"DRAFT_COMMIT_NOT_IMMUTABLE")

def _pin(blobs,pins):
    _require(type(blobs) is dict and set(blobs)==set(LIMITS),"DRAFT_MATERIAL_NOT_AVAILABLE")
    _require(type(pins) is tuple and len(pins)==len(LIMITS),"DRAFT_PIN_CONFIG_INVALID")
    parsed={}
    for row in pins:
        _require(type(row) is tuple and len(row)==3,"DRAFT_PIN_CONFIG_INVALID")
        k,n,h=row
        _require(type(k) is str and k in LIMITS and k not in parsed and _int(n,1,LIMITS[k]) and _hex(h),"DRAFT_PIN_CONFIG_INVALID")
        parsed[k]=(n,h)
    for k,b in blobs.items():
        _require(type(b) is bytes and len(b)>0,"DRAFT_MATERIAL_NOT_AVAILABLE")
        _require(len(b)<=LIMITS[k],"DRAFT_INPUT_LIMIT")
        _require(parsed[k]==(len(b),_sha(b)),"DRAFT_ARTIFACT_PIN_MISMATCH")
    return parsed

def _members(archive):
    """Bounded gzip/tar reader; reuses archive path policy, never extracts.

    Existing ZIP extraction cannot read npm tgz. This reader accepts ordinary
    files/directories only; extension headers, links and special nodes reject.
    """
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive),mode="rb") as f:
            raw=f.read(1048577)
        _require(len(raw)<=1048576,"DRAFT_ARCHIVE_LIMIT")
        _require(len(raw)%512==0,"DRAFT_ARCHIVE_INVALID")
        offset,count,seen,files=0,0,set(),{}
        while offset+512<=len(raw):
            header=raw[offset:offset+512]
            if header==b"\0"*512:
                _require(len(raw)-offset>=1024 and not any(raw[offset:]),"DRAFT_ARCHIVE_INVALID")
                return files
            m=tarfile.TarInfo.frombuf(header,"utf-8","strict")
            count+=1
            _require(count<=100,"DRAFT_ARCHIVE_LIMIT")
            _require(m.type in (tarfile.REGTYPE,tarfile.AREGTYPE,tarfile.DIRTYPE),"DRAFT_ARCHIVE_TYPE")
            try:
                path=normalize_member_path(m.name,is_directory=m.isdir(),limits=ZipSafetyLimits())
            except IngestionSecurityError:
                raise DraftError("DRAFT_ARCHIVE_PATH") from None
            _require(path.parts[0]=="package" and (len(path.parts)>1 or m.isdir()),"DRAFT_ARCHIVE_PATH")
            _require(path.collision_key not in seen,"DRAFT_ARCHIVE_DUPLICATE")
            seen.add(path.collision_key)
            _require(0<=m.size<=65536 and (not m.isdir() or m.size==0),"DRAFT_ARCHIVE_LIMIT")
            start=offset+512;end=start+m.size;offset=start+((m.size+511)//512)*512
            _require(offset<=len(raw) and not any(raw[end:offset]),"DRAFT_ARCHIVE_INVALID")
            if m.isfile():
                files[path.relative_path]=raw[start:end]
        raise DraftError("DRAFT_ARCHIVE_INVALID")
    except (OSError,EOFError,tarfile.TarError,UnicodeError,ValueError,zlib.error) as exc:
        if isinstance(exc,DraftError):
            raise
        raise DraftError("DRAFT_ARCHIVE_INVALID") from None

def _receipt_record(record,url,data):
    _require(type(record) is dict and record.get("url")==url,"DRAFT_SOURCE_URL_MISMATCH")
    _require(type(record.get("status")) is int and record["status"]==200 and
             type(record.get("bytes")) is int and type(record.get("utc")) is str,"DRAFT_RECEIPT_INVALID")
    try:
        dt=datetime.fromisoformat(record["utc"].replace("Z","+00:00"))
        _require(dt.utcoffset() is not None and dt.utcoffset().total_seconds()==0,"DRAFT_RECEIPT_INVALID")
    except ValueError as exc:
        if isinstance(exc,DraftError):
            raise
        raise DraftError("DRAFT_RECEIPT_INVALID") from None
    _require(record["bytes"]==len(data) and record.get("sha256")==_sha(data),"DRAFT_RECEIPT_HASH_MISMATCH")

def _event(history,index,method,path,status):
    _require(type(history) is list and _int(index,0,len(history)-1),"DRAFT_HISTORY_BINDING_MISMATCH")
    e=history[index]
    _require(type(e) is dict and e.get("method")==method and e.get("path")==path and
             type(e.get("status")) is int and e["status"]==status and type(e.get("response")) is dict,"DRAFT_HISTORY_BINDING_MISMATCH")
    return e["response"]

def _history(c,history,indices,license_bytes):
    _require(type(indices) is tuple and len(indices)==5 and all(_int(i) for i in indices) and len(set(indices))==5,"DRAFT_HISTORY_BINDING_MISMATCH")
    b,s=c["binding"],c["subject"]
    prefix="/api/v1/scans/"+b["scan_id"];ap=prefix+"/assessments/"+b["assessment_id"]
    scan=_event(history,indices[0],"GET",prefix,200)
    resources=_event(history,indices[1],"GET",prefix+"/resources",200)
    a=_event(history,indices[2],"GET",ap,200)
    bound=_event(history,indices[3],"GET",ap+"/p2/binding",200)
    saved=_event(history,indices[4],"POST",ap+"/p2/materials",201)
    _require(_canonical(bound)==_canonical(b),"DRAFT_HISTORY_BINDING_MISMATCH")
    for ak,bk in (("id","assessment_id"),("version","assessment_version"),("scan_id","scan_id"),
                  ("facts_hash","facts_hash"),("usage_hash","usage_hash"),("rule_version","rule_version")):
        _require(type(a.get(ak)) is type(b[bk]) and a[ak]==b[bk],"DRAFT_HISTORY_BINDING_MISMATCH")
    _require(scan.get("scan_id")==b["scan_id"] and scan.get("status")==a.get("scan_status"),"DRAFT_HISTORY_BINDING_MISMATCH")
    _require(s["resource_id"] in a.get("resource_ids",[]),"DRAFT_HISTORY_BINDING_MISMATCH")
    matches=[v["resource"] for v in resources.get("items",[]) if type(v) is dict and
             type(v.get("resource")) is dict and v["resource"].get("id")==s["resource_id"]]
    _require(len(matches)==1,"DRAFT_HISTORY_BINDING_MISMATCH")
    resource=matches[0]
    _require(resource.get("name")==s["name"] and resource.get("version")==s["version"] and resource.get("ecosystem")=="npm","DRAFT_HISTORY_BINDING_MISMATCH")
    m,r=saved.get("material"),saved.get("result")
    _require(type(m) is dict and type(r) is dict,"DRAFT_HISTORY_BINDING_MISMATCH")
    for x in (m,r):
        _require(_canonical(x.get("binding"))==_canonical(b) and x.get("data_scope")=="TEST_ONLY" and x.get("formal_effect")=="none","DRAFT_HISTORY_BINDING_MISMATCH")
    _require(m.get("subject")==dict(resource_id=s["resource_id"],version=s["version"]),"DRAFT_HISTORY_BINDING_MISMATCH")
    _require(m.get("verification_state")=="pending" and m.get("source_level")=="user_supplied_unverified" and
             m.get("adoption_status")=="adopted_as_unverified_observation","DRAFT_PRIOR_MATERIAL_NOT_OBSERVATION")
    _require(m.get("filename")=="LICENSE" and m.get("source_sha256")==_sha(license_bytes) and
             type(m.get("byte_count")) is int and m["byte_count"]==len(license_bytes),"DRAFT_MEMBER_HASH_MISMATCH")
    ev=m.get("evidence_ids")
    _require(type(ev) is list and len(ev)>0 and all(_id(i) for i in ev) and len(set(ev))==len(ev) and
             set(ev)<=set(resource.get("evidence_ids",[])) and set(ev)<=set(a.get("evidence_ids",[])),"DRAFT_EVIDENCE_BINDING_MISMATCH")
    _require(r.get("result_id")==c["prior_result_id"] and type(r.get("revision")) is int and
             r["revision"]==c["prior_result_revision"] and _id(m.get("material_id")) and
             m["material_id"] in r.get("material_ids",[]),"DRAFT_HISTORY_BINDING_MISMATCH")
    rr=[v for v in r.get("resources",[]) if type(v) is dict and v.get("subject")==m["subject"]]
    _require(len(rr)==1 and m["material_id"] in rr[0].get("material_ids",[]) and set(ev)<=set(rr[0].get("evidence_ids",[])),"DRAFT_EVIDENCE_BINDING_MISMATCH")
    _require(_sha(_canonical({k:v for k,v in r.items() if k!="result_sha256"}))==r.get("result_sha256"),"DRAFT_PRIOR_RESULT_HASH_MISMATCH")
    _require(type(a.get("usage")) is dict and type(r.get("usage")) is dict,"DRAFT_USAGE_MISMATCH")
    for x in (a["usage"],r["usage"]):
        _require(all(k in x and (x[k] is None or type(x[k]) is bool) and x[k] is c["usage"][k] for k in USES),"DRAFT_USAGE_MISMATCH")
    return scan,a,m,r,ev

def validate_draft(claim: bytes, *, pins: tuple, blobs: dict, event_indices: tuple) -> dict:
    """Pure fixed-release observation. Pins and event selectors are task-owned.

    pins = (artifact name, byte count, SHA256) tuples. Never accept these as
    uploader-provided authority. history records are pinned observations, not
    reconstructed raw HTTP or independent recomputation of Formal hashes.
    """
    try:
        return _validate(claim,pins,blobs,event_indices)
    except (KeyError,TypeError,IndexError,AttributeError,RecursionError):
        raise DraftError("DRAFT_INPUT_INVALID") from None

def _validate(claim,pins,blobs,indices):
    _require(type(claim) is bytes and 0<len(claim)<=16384,"DRAFT_INPUT_LIMIT")
    c=_json(claim);_check_claim(c)
    _require(type(blobs) is dict and type(blobs.get("license")) is bytes and bool(blobs["license"]),"DRAFT_MATERIAL_NOT_AVAILABLE")
    _require(len(blobs["license"])<=LIMITS["license"],"DRAFT_INPUT_LIMIT")
    _text(blobs["license"])
    pinned=_pin(blobs,pins)
    scan,a,m,r,ev=_history(c,_json(blobs["history"]),indices,blobs["license"])
    _require(c["subject"]["name"]=="is-number" and c["subject"]["version"]=="7.0.0","DRAFT_PACKAGE_MISMATCH")
    receipts=_json(blobs["receipts"])
    _require(type(receipts) is list and c["source_receipt_index"]<len(receipts),"DRAFT_RECEIPT_INVALID")
    rec=receipts[c["source_receipt_index"]]
    _require(type(rec) is dict and rec.get("package")=="is-number" and rec.get("version")=="7.0.0","DRAFT_PACKAGE_MISMATCH")
    _receipt_record(rec.get("metadata"),META_URL,blobs["metadata"])
    _receipt_record(rec.get("tarball"),TAR_URL,blobs["archive"])
    for row in (rec["metadata"],rec["tarball"]):
        _require("method" not in row or row["method"]=="GET","DRAFT_RECEIPT_INVALID")
        _require("request_method" not in row or row["request_method"]=="GET","DRAFT_RECEIPT_INVALID")
    meta=_json(blobs["metadata"])
    _require(type(meta) is dict and meta.get("name")=="is-number" and meta.get("version")=="7.0.0","DRAFT_PACKAGE_MISMATCH")
    dist=meta.get("dist")
    _require(type(dist) is dict and dist.get("tarball")==TAR_URL,"DRAFT_SOURCE_URL_MISMATCH")
    integrity="sha512-"+base64.b64encode(hashlib.sha512(blobs["archive"]).digest()).decode()
    _require(dist.get("integrity")==integrity,"DRAFT_NPM_INTEGRITY_MISMATCH")
    files=_members(blobs["archive"])
    _require("package/LICENSE" in files and "package/package.json" in files,"DRAFT_REQUIRED_MEMBER_MISSING")
    pkg=_json(files["package/package.json"])
    _require(type(pkg) is dict and pkg.get("name")=="is-number" and pkg.get("version")=="7.0.0","DRAFT_PACKAGE_MISMATCH")
    _require(files["package/LICENSE"]==blobs["license"],"DRAFT_MEMBER_HASH_MISMATCH")
    declared=[v for v in rec.get("members",[]) if type(v) is dict and v.get("member")=="package/LICENSE"]
    _require(len(declared)==1 and type(declared[0].get("bytes")) is int and
             declared[0]["bytes"]==len(blobs["license"]) and declared[0].get("sha256")==_sha(blobs["license"]),"DRAFT_MEMBER_HASH_MISMATCH")
    gaps={"A_TRUSTED_ISSUANCE_MISSING","OWNER_APPLICABILITY_SIGNATURE_MISSING","SCAN_TO_RELEASE_SCOPE_UNVERIFIED",
          "CLAUSE_SEMANTICS_NOT_REVIEWED","SOURCE_PRODUCER_UNVERIFIED","SOURCE_POLICY_UNAPPROVED",
          "REPOSITORY_COMMIT_ASSOCIATION_UNVERIFIED","HISTORICAL_OBSERVATION_NOT_NEW_FACT"}
    for key,prefix in (("source_status","SOURCE"),("owner_scope_status","OWNER_SCOPE")):
        if c[key] in ("rejected","conflict","revoked"):
            gaps.add(prefix+"_"+c[key].upper())
    if scan.get("status")=="partial" or a.get("coverage_issues"):
        gaps.add("SCAN_PARTIAL_COVERAGE")
    elif scan.get("status")!="completed":
        gaps.add("SCAN_COVERAGE_UNESTABLISHED")
    if all(v is None for v in c["usage"].values()):
        gaps.add("USAGE_ALL_UNSPECIFIED")
    elif any(v is None for v in c["usage"].values()):
        gaps.add("USAGE_PARTIALLY_UNSPECIFIED")
    if not any(v is True for v in c["usage"].values()):
        gaps.add("NO_EXPLICIT_SELECTED_USE")
    if not any(k.rsplit("/",1)[-1].upper().split(".")[0]=="NOTICE" for k in files):
        gaps.add("NOTICE_NOT_OBSERVED_NOT_NO_OBLIGATION")
    method="HISTORICAL_GET_RECORDED" if all(v.get("request_method",v.get("method"))=="GET" for v in (rec["metadata"],rec["tarball"])) else "UNKNOWN_IN_PINNED_RECEIPT"
    if method=="UNKNOWN_IN_PINNED_RECEIPT":
        gaps.add("HISTORICAL_METHOD_NOT_RECORDED")
    o=dict(version=VERSION,state="DRAFT_OBSERVATION",evidence_level="PINNED_HISTORICAL_BYTE_CONSISTENCY_ONLY",
           data_scope="TEST_ONLY",binding=c["binding"],subject=c["subject"],usage=c["usage"],
           source_observation_ref="sha256:"+_sha(blobs["receipts"])+"#/"+str(c["source_receipt_index"]),
           source_receipt_sha256=_sha(blobs["receipts"]),retrieval_method=method,
           metadata=dict(url=META_URL,bytes=len(blobs["metadata"]),sha256=_sha(blobs["metadata"]),utc=rec["metadata"]["utc"]),
           archive=dict(url=TAR_URL,bytes=len(blobs["archive"]),sha256=_sha(blobs["archive"]),utc=rec["tarball"]["utc"]),
           license_member=dict(path="package/LICENSE",bytes=len(blobs["license"]),sha256=_sha(blobs["license"])),
           technical_binding="MATCHED_LOCAL_BYTES_AND_PINNED_HISTORY",
           source_declared_status=c["source_status"],owner_declared_status=c["owner_scope_status"],
           source_issuance="MISSING" if c["source_status"]=="missing" else "UNVERIFIED",
           owner_scope="MISSING" if c["owner_scope_status"]=="missing" else "UNVERIFIED",
           policy_state="UNAPPROVED",repository_commit_state="UNVERIFIED",
           prior_result_id=r["result_id"],prior_result_revision=r["revision"],prior_material_id=m["material_id"],
           evidence_ids=ev,history_sha256=_sha(blobs["history"]),history_event_indices=list(indices),
           source_pins={k:dict(bytes=v[0],sha256=v[1]) for k,v in pinned.items()},
           gaps=sorted(gaps),new_fact_count=0,positive_advice=[],formal_effect="none",
           public_contract_approved=False,m1_complete=False)
    o["draft_id"]="draft_"+_sha(_canonical(o))
    return o
