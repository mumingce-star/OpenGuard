import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const taxonomy = "benchmarks/taxonomies/b06-fn-fp-taxonomy.json";
const ledger = "benchmarks/taxonomies/b06-rule-improvement-ledger.json";
const validator = "benchmarks/taxonomies/validate-b06-rule-improvement-ledger.mjs";

test("B06 错误分析台账要求 FN tier、FP 分类及冻结前 holdout 门禁", async () => {
  const output = execFileSync("node", [validator, taxonomy, ledger], { encoding: "utf8" });
  const result = JSON.parse(output);
  assert.equal(result.valid, true);
  assert.equal(result.gold_frozen, false);
  assert.equal(result.formal_metrics_claimed, false);

  const sandbox = await mkdtemp(join(tmpdir(), "openguard-b06-ledger-"));
  const altered = JSON.parse(await readFile(ledger, "utf8"));
  altered.rule_changes[0].generic_rule_id = "repository_whitelist_for_candidate";
  const alteredPath = join(sandbox, "ledger.json");
  await writeFile(alteredPath, JSON.stringify(altered), "utf8");
  assert.throws(
    () => execFileSync("node", [validator, taxonomy, alteredPath], { encoding: "utf8", stdio: "pipe" }),
    /Command failed/,
  );
});
