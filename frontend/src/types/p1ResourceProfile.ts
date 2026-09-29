import type { FactVerification } from "./domain";

export type ProfileVerification = Exclude<FactVerification, "unknown">;

export interface ProfileEvidenceRef {
  namespace: "scan" | "profile_observation";
  scan_id?: string;
  evidence_id?: string;
  observation_id?: string;
}

export interface ProfileLicenseObservation {
  license_expression_id: string;
  expression: string;
  relation_scope: string;
  evidence_refs: ProfileEvidenceRef[];
  verification_status: ProfileVerification;
}

export interface ProfileMetadataField {
  name: string;
  value: string | null;
  locator: string;
  verification_status: ProfileVerification;
}

export interface ProfileMetadataObservation {
  observation_id: string;
  provider: string;
  resource_identity_key: string;
  requested_revision: string | null;
  resolved_revision: string | null;
  source_url: string;
  fetched_at: string;
  content_hash: string;
  parser_version: string;
  bounded_excerpt: string;
  fields: ProfileMetadataField[];
  verification_status: ProfileVerification;
  coverage_gaps: string[];
  full_response_replay_available: false;
}

export interface ResourceProfile {
  schema_version: "1.0";
  profile_id: string;
  scan_ref: {
    scan_id: string;
    revision: string | null;
    facts_hash: string;
    input_hash: string;
    inventory_hash: string | null;
    status: string;
    registry_revision: number;
  };
  resource_ref: {
    scan_id: string;
    resource_kind: "component" | "ai_asset";
    resource_id: string;
    resource_identity_key: string | null;
    resource_instance_key: string | null;
  };
  identity: {
    name: string;
    version: string | null;
    ecosystem: string | null;
    provider: string | null;
    source_url: string | null;
  };
  license_observations: ProfileLicenseObservation[];
  authorization_fact: {
    status: ProfileVerification;
    source_ref: { scan_id: string; pointer: string };
  } | null;
  metadata_observations: ProfileMetadataObservation[];
  coverage_gaps: string[];
  evidence_refs: ProfileEvidenceRef[];
  provenance: Record<string, unknown>;
}

export type ProfileRefreshStatus = "pending" | "succeeded" | "failed";

export interface ProfileRefreshItem {
  resource_id: string;
  status: ProfileRefreshStatus;
  observation_id: string | null;
  error_code: string | null;
}

export interface ProfileRefreshJob {
  schema_version: "1.0";
  job_id: string;
  scan_id: string;
  facts_hash: string;
  resource_ids: string[];
  status: ProfileRefreshStatus;
  items: ProfileRefreshItem[];
  created_at: string;
  completed_at: string | null;
  algorithm_version: string;
}

export type ResourceProfileState =
  | { status: "loading" }
  | { status: "ready"; profile: ResourceProfile }
  | { status: "missing"; detail: string }
  | { status: "error"; detail: string };
