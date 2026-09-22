import type { Evidence, FactVerification, Resource } from "../types/domain";
import type { ResourceProfile } from "../types/p1ResourceProfile";
import { resolvedProfileRevision } from "./p1ResourceProfiles";

export interface ResourceCardFacts {
  provider: string | null;
  version: string | null;
  revision: string | null;
  revisionConflicted: boolean;
  license: string | null;
  licenseConflicted: boolean;
  licenseVerification: FactVerification;
  authorization: FactVerification;
  evidence: Evidence[];
  missingEvidenceIds: string[];
  association: null;
  missing: string[];
}

export function resourceCardFacts(resource: Resource, profile: ResourceProfile | null, evidence: Evidence[]): ResourceCardFacts {
  const revision = resolvedProfileRevision(profile);
  const entries = evidence.filter(item => resource.evidenceIds.includes(item.id));
  const present = new Set(entries.map(item => item.id));
  const missingEvidenceIds = resource.evidenceIds.filter(id => !present.has(id));
  const observations = profile?.license_observations ?? [];
  const licenseConflicted = new Set(observations.map(item => `${item.expression}\u0000${item.verification_status}`)).size > 1;
  const profileLicense = licenseConflicted ? undefined : observations[0];
  const provider = profile?.identity.provider ?? resource.provider ?? null;
  const version = profile?.identity.version ?? resource.version ?? null;
  const license = licenseConflicted ? null : profileLicense?.expression ?? resource.license ?? null;
  const licenseVerification = licenseConflicted ? "unknown" : profileLicense?.verification_status ?? resource.licenseVerification ?? "unknown";
  const authorization = profile?.authorization_fact?.status ?? resource.authorizationStatus ?? "unknown";
  const missing: string[] = [];
  if (!provider) missing.push("provider 未获取");
  if (!version) missing.push("version 未获取");
  if (!revision.value) missing.push(revision.conflicted ? "revision 观测冲突" : "revision 未获取");
  if (licenseConflicted) missing.push("许可观测冲突，证据不足");
  else if (!license) missing.push("观测许可未获取");
  if (licenseVerification === "unknown") missing.push("许可核验状态未知");
  if (authorization === "unknown") missing.push("授权状态未知");
  if (!profile) missing.push("Resource Profile 未提供");
  if (!profile?.resource_ref.resource_identity_key) missing.push("Profile 身份键未获取");
  if (!profile?.resource_ref.resource_instance_key) missing.push("Profile 实例键未获取");
  if (!entries.length || missingEvidenceIds.length) missing.push("Evidence 证据不足");
  missing.push("模型与数据集关联未获取");
  for (const gap of profile?.coverage_gaps ?? []) if (!missing.includes(gap)) missing.push(gap);
  return {
    provider,
    version,
    revision: revision.value,
    revisionConflicted: revision.conflicted,
    license,
    licenseConflicted,
    licenseVerification,
    authorization,
    evidence: entries,
    missingEvidenceIds,
    association: null,
    missing,
  };
}

export function evidenceSources(items: Evidence[]): string[] {
  return [...new Set(items.map(item => item.source).filter(Boolean))];
}
