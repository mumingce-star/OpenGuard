import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
const path = process.argv[2]; if (!path) throw new Error("usage: node validate-amendment.mjs <amendment.json>");
const value = JSON.parse(await readFile(path, "utf8")); const errors=[];
if (!Array.isArray(value.amendments) || value.amendments.length===0) errors.push("amendments required");
for (const amendment of value.amendments ?? []) {
  if (!amendment.target_type || !amendment.target_id || !amendment.reason_code || !amendment.artifact_path || !amendment.previous_artifact_path || !amendment.old_sha256 || !amendment.new_sha256) errors.push("target, current/previous artifact paths, reason and old/new hashes required");
  if (!/^[a-f0-9]{64}$/.test(amendment.old_sha256 ?? "") || !/^[a-f0-9]{64}$/.test(amendment.new_sha256 ?? "")) errors.push("amendment hashes must be lowercase SHA-256 values");
  if (amendment.artifact_path) try {
    const artifact = await readFile(resolve(dirname(path), amendment.artifact_path));
    const actual = createHash("sha256").update(artifact).digest("hex");
    if (actual !== amendment.new_sha256) errors.push(`new SHA-256 does not match target artifact: ${amendment.target_id}`);
  } catch { errors.push(`target artifact is unreadable: ${amendment.target_id}`); }
  if (amendment.previous_artifact_path) try {
    const artifact = await readFile(resolve(dirname(path), amendment.previous_artifact_path));
    const actual = createHash("sha256").update(artifact).digest("hex");
    if (actual !== amendment.old_sha256) errors.push(`old SHA-256 does not match previous target artifact: ${amendment.target_id}`);
  } catch { errors.push(`previous target artifact is unreadable: ${amendment.target_id}`); }
  if (amendment.proposed_by?.type !== "human" || !amendment.proposed_by?.reviewer_id) errors.push("a named human proposer is required");
  if (amendment.approved_by?.type !== "human" || !amendment.approved_by?.reviewer_id) errors.push("AI or missing approval cannot approve an amendment");
  if (amendment.approved_by?.reviewer_id === amendment.proposed_by?.reviewer_id) errors.push("proposer cannot be sole amendment approver");
}
console.log(JSON.stringify({valid:!errors.length,errors})); process.exitCode=errors.length?1:0;
