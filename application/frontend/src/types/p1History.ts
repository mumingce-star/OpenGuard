import type { ScanStatus } from "./domain";

export type HistorySourceType = "git" | "zip" | "local";

export interface HistoryProjectIdentity {
  method: "canonical_github_repo_v1" | "scan_only";
  key: string;
  source_project_id: string;
}

export interface HistoryAssessmentRef {
  assessment_id: string;
  version: number;
  scan_id: string;
  facts_hash: string;
  usage_hash: string;
  rule_version: string;
  formal: true;
}

export interface HistoryFindingCounts {
  pass: number;
  warning: number;
  review_required: number;
  unknown: number;
}

export interface ScanHistoryItem {
  schema_version: "1.0";
  scan_id: string;
  project_identity: HistoryProjectIdentity;
  source_type: HistorySourceType;
  source: string;
  revision: string | null;
  input_hash: string;
  inventory_hash: string | null;
  status: ScanStatus;
  stage:
    | "queued"
    | "ingestion"
    | "inventory"
    | "scan"
    | "normalize"
    | "rules"
    | "ai_assist"
    | "report"
    | "completed";
  created_at: string;
  finished_at: string | null;
  component_count: number;
  ai_asset_count: number;
  finding_count: number;
  summary: {
    component_count: number;
    ai_asset_count: number;
    evidence_count: number;
    finding_counts: HistoryFindingCounts;
  };
  latest_assessment: HistoryAssessmentRef | null;
  provenance: {
    producer: { name: string; version: string };
    source_refs: Array<{
      scan_id: string;
      revision: string | null;
      facts_hash: string;
      input_hash: string;
      inventory_hash: string | null;
      status: ScanStatus;
      registry_revision: number;
    }>;
    assessment_refs: HistoryAssessmentRef[];
    generated_at: string;
    algorithm_version: string;
    parameters_hash: string;
  };
}

export interface HistoryPage {
  schema_version: "1.0";
  items: ScanHistoryItem[];
  next_cursor: string | null;
}

export interface HistoryQuery {
  cursor?: string;
  limit: number;
  status?: ScanStatus;
  sourceType?: HistorySourceType;
  q?: string;
  projectKey?: string;
}
