import { readFile } from "node:fs/promises";
import { DIMENSIONS, parseArgs, sha256, validatePacket, writeJsonExclusive } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.packet || !args.output) throw new Error("用法: node prepare-review-form.mjs --packet <盲化包> --output <私有复标表>");
const packetText = await readFile(args.packet, "utf8");
const packet = JSON.parse(packetText);
const errors = validatePacket(packet);
if (errors.length) throw new Error(errors.join("\n"));
const emptyDimensions = () => Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, null]));
const form = {
  schema_version: "openguard-single-human-rereview/0.1",
  status: "draft",
  batch_id: packet.batch_id,
  review_cycle: 2,
  first_round_confirmation_id: "hrv_20260911_user_01",
  blind_packet_sha256: sha256(packetText),
  reviewer: {
    type: "human",
    reviewer_id: null,
    identity_mode: "self_reported_single_human",
    attestation: {
      same_human_as_first_review: null,
      prior_ai_and_system_exposure_disclosed: null,
      previous_labels_not_accessed_during_rereview: null,
      review_completed_without_ai_label_suggestions: null,
      understands_not_independent_second_human: null
    }
  },
  rereview_started_at: null,
  submitted_at: null,
  records: packet.records.map((record) => ({
    record_id: record.record_id,
    judgments: emptyDimensions(),
    rationales: emptyDimensions(),
    evidence_locators: [],
    notes: null
  }))
};
const result = await writeJsonExclusive(args.output, form);
console.log(JSON.stringify({ output: result.destination, sha256: result.sha256, records: form.records.length }));
