import { readFile } from "node:fs/promises";

const path = process.argv[2];
if (!path) throw new Error("usage: node validate-b06-fn-fp-taxonomy.mjs <taxonomy.json>");
const taxonomy = JSON.parse(await readFile(path, "utf8"));
const expected = ["FP_LICENSE_EXPRESSION", "FP_NOTICE_SUBSTITUTION", "FP_SOURCE_MISMATCH", "FN_MISSING_LICENSE", "FN_MISSING_NOTICE", "FN_MISSING_COPYRIGHT", "FN_SOURCE_RELATION"];
const codes = (taxonomy.categories ?? []).map((item) => item.code).sort();
const errors = [];
if (taxonomy.schema_version !== "openguard-b06-fn-fp-taxonomy/1") errors.push("unsupported taxonomy schema");
if (taxonomy.status !== "draft_not_gold") errors.push("taxonomy must not represent frozen Gold");
if (JSON.stringify(codes) !== JSON.stringify([...expected].sort())) errors.push("taxonomy category set is incomplete or contains unknown codes");
console.log(JSON.stringify({ valid: errors.length === 0, errors, category_count: codes.length, gold_frozen: false }));
process.exitCode = errors.length ? 1 : 0;
