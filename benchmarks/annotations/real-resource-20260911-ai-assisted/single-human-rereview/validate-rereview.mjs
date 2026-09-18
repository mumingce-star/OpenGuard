import { readFile } from "node:fs/promises";
import { parseArgs, readJson, sha256, validateReview } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.packet || !args.review) throw new Error("用法: node validate-rereview.mjs --packet <盲化包> --review <复标回执>");
const packetText = await readFile(args.packet, "utf8");
const [packet, review] = await Promise.all([Promise.resolve(JSON.parse(packetText)), readJson(args.review)]);
const { errors, warnings } = validateReview(packetText, packet, review, 72);
console.log(JSON.stringify({ valid: errors.length === 0, errors, warnings, packet_sha256: sha256(packetText), records: review.records?.length ?? 0 }, null, 2));
process.exitCode = errors.length ? 1 : 0;
