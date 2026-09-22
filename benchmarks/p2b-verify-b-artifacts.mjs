import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";

const args=process.argv.slice(2); const option=(name)=>{const index=args.indexOf(name); return index < 0 ? undefined : args[index+1];};
const baselinePath=option("--baseline"), writeBaselinePath=option("--write-baseline");
const root = process.cwd(); const targets = ["benchmarks", "tests/fixtures", "docs/p1", "docs/spec"];
const files = [];
async function walk(path) { for (const item of await readdir(path, { withFileTypes:true })) { const full=join(path,item.name); if (item.isDirectory()) await walk(full); else if (item.name !== "p2b-b-artifacts-baseline.json" && /\.(json|jsonl|mjs|md)$/.test(item.name)) files.push(full); } }
for (const target of targets) await walk(join(root,target));
const diagnostics=[]; const rows=[]; let sourceBindingsChecked=0;
for (const file of files.sort()) { const body=await readFile(file); const text=body.toString("utf8"); const path=relative(root,file).replaceAll("\\","/");
  if (/AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}/.test(text)) diagnostics.push({code:"SENSITIVE_CONTENT",path});
  // Bench fixture payload fragments intentionally omit enclosing JSON punctuation;
  // their owning manifest validates them as artifacts, so do not misclassify them.
  const opaqueFixture = /benchmarks\/examples\/v2\/(?:valid|invalid)\/fixtures\//.test(path);
  if (file.endsWith(".json") && !opaqueFixture) { try {
    const payload=JSON.parse(text);
    if (Object.hasOwn(payload,"provenance")) {
      const provenance=payload.provenance;
      const direct = provenance && /^[a-f0-9]{64}$/.test(provenance.source_sha256 ?? "") && typeof provenance.source_commit === "string" && provenance.source_commit && typeof provenance.source_index_artifact_id === "string" && provenance.source_index_artifact_id;
      const scanRefs = provenance?.source_refs;
      const referenced = Array.isArray(scanRefs) && scanRefs.length > 0 && scanRefs.every((ref) => typeof ref.scan_id === "string" && ref.scan_id && /^[a-f0-9]{40}$/.test(ref.revision ?? "") && /^[a-f0-9]{64}$/.test(ref.facts_hash ?? "") && /^[a-f0-9]{64}$/.test(ref.input_hash ?? "") && /^[a-f0-9]{64}$/.test(ref.inventory_hash ?? ""));
      if (!direct && !referenced) diagnostics.push({code:"SOURCE_PROVENANCE_INVALID",path}); else sourceBindingsChecked++;
    }
    if (Object.hasOwn(payload,"source_file_sha256")) {
      const hashes=payload.source_file_sha256;
      const validHash = (hash) => /^[a-f0-9]{64}$/.test(hash ?? "");
      if (!(typeof hashes === "string" ? validHash(hashes) : hashes && typeof hashes === "object" && Object.values(hashes).length > 0 && Object.values(hashes).every(validHash))) diagnostics.push({code:"SOURCE_HASH_INVALID",path}); else sourceBindingsChecked++;
    }
  } catch { diagnostics.push({code:"INVALID_JSON",path}); } }
  rows.push({path,sha256:createHash("sha256").update(body).digest("hex"),size_bytes:body.length});
}
const stable = rows.every((row,index)=>index===0 || rows[index-1].path < row.path);
const baseline={schema:"openguard.p2b.b-artifact-baseline/1",artifacts:rows};
if (writeBaselinePath) await writeFile(writeBaselinePath, `${JSON.stringify(baseline,null,2)}\n`, "utf8");
let driftChecked=false;
if (baselinePath) { const expected=JSON.parse(await readFile(baselinePath,"utf8")); const expectedRows=expected.artifacts; if (!Array.isArray(expectedRows)) diagnostics.push({code:"BASELINE_INVALID"}); else { driftChecked=true; if (JSON.stringify(expectedRows)!==JSON.stringify(rows)) diagnostics.push({code:"FIXTURE_DRIFT"}); } }
else if (!writeBaselinePath) diagnostics.push({code:"BASELINE_REQUIRED"});
console.log(JSON.stringify({schema:"openguard.p2b.delivery-gate/1",valid:diagnostics.length===0 && stable,artifact_count:rows.length,source_bindings_checked:sourceBindingsChecked,stable_sort:stable,fixture_drift_checked:driftChecked,diagnostics,artifacts:rows},null,2));
process.exitCode=diagnostics.length || !stable ? 1 : 0;
