import { readFile } from 'node:fs/promises';

const [taxonomyPath, ledgerPath] = process.argv.slice(2);
if (!taxonomyPath || !ledgerPath) throw new Error('usage: node validate-b06-rule-improvement-ledger.mjs <taxonomy.json> <ledger.json>');
const taxonomy = JSON.parse(await readFile(taxonomyPath, 'utf8'));
const ledger = JSON.parse(await readFile(ledgerPath, 'utf8'));
const categories = new Map((taxonomy.categories ?? []).map((item) => [item.code, item]));
const errors = [];
if (ledger.schema_version !== 'openguard-b06-rule-improvement-ledger/1' || ledger.status !== 'draft_not_gold') errors.push('ledger must remain draft_not_gold');
if (ledger.holdout_policy !== 'blocked_until_human_gold_freeze') errors.push('holdout policy must remain blocked before Gold freeze');
if (!Array.isArray(ledger.rule_changes) || !ledger.rule_changes.length) errors.push('at least one generic rule change is required');
const seen = new Set();
for (const change of ledger.rule_changes ?? []) {
  if (!/^[a-z][a-z0-9-]{2,127}$/.test(change.change_id ?? '') || seen.has(change.change_id)) errors.push('change_id');
  seen.add(change.change_id);
  if (!/^[a-z][a-z0-9_]{2,127}$/.test(change.generic_rule_id ?? '')) errors.push('generic_rule_id');
  const encoded = JSON.stringify(change).toLowerCase();
  if (/(github\.com|repository|repo[_-]?id|whitelist|allowlist)/.test(encoded)) errors.push('repository-specific allowlist is forbidden');
  for (const field of ['improves', 'collateral_risk']) {
    if (!Array.isArray(change[field]) || !change[field].length || change[field].some((code) => !categories.has(code))) errors.push(field);
  }
  if (change.improves?.some((code) => !['false_positive', 'false_negative'].includes(categories.get(code)?.kind))) errors.push('improves taxonomy');
  const holdout = change.holdout_validation;
  if (!holdout || holdout.split !== 'holdout' || holdout.family_policy !== 'unseen_family' || holdout.status !== 'blocked_until_human_gold_freeze') errors.push('holdout_validation');
}
for (const category of categories.values()) {
  if (category.kind === 'false_negative' && !['A', 'B', 'C'].includes(category.tier)) errors.push('FN tier');
  if (category.kind === 'false_positive' && typeof category.classification !== 'string') errors.push('FP classification');
}
console.log(JSON.stringify({valid: errors.length === 0, errors: [...new Set(errors)], gold_frozen: false, formal_metrics_claimed: false}));
process.exitCode = errors.length ? 1 : 0;
