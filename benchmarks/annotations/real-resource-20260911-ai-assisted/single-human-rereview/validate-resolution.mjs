import { readFile } from "node:fs/promises";
import { parseArgs, readJson, sha256, validateResolution } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.comparison || !args.resolution) throw new Error("用法: node validate-resolution.mjs --comparison <比较结果> --resolution <冲突复核>");
const comparisonText = await readFile(args.comparison, "utf8");
const [comparison, resolution] = await Promise.all([Promise.resolve(JSON.parse(comparisonText)), readJson(args.resolution)]);
const errors = validateResolution(comparisonText, comparison, resolution);
console.log(JSON.stringify({ valid: errors.length === 0, errors, comparison_sha256: sha256(comparisonText), conflicts: resolution.records?.length ?? 0 }, null, 2));
process.exitCode = errors.length ? 1 : 0;
