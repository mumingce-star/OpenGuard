import { useEffect, useRef, useState } from "react";
import type { Resource, Scan } from "../types/domain";
import { factVerificationLabels } from "../types/domain";
import type { ResourceProfileState } from "../types/p1ResourceProfile";
import { getResourceProfile, refreshResourceProfile } from "../services/p1ResourceProfiles";
import { evidenceSources, resourceCardFacts } from "../services/resourceCardPresentation";

function FactBadge({ value }: { value: keyof typeof factVerificationLabels }) {
  return <span className={`og-fact-status ${value}`}>{factVerificationLabels[value]}</span>;
}

export function AIResourceCard({
  scan,
  resource,
  onEvidence,
}: {
  scan: Scan;
  resource: Resource;
  onEvidence: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");
  const refreshKey = useRef(crypto.randomUUID());
  const [profileState, setProfileState] = useState<ResourceProfileState>(() =>
    scan.mode === "api"
      ? { status: "loading" }
      : { status: "missing", detail: "演示模式不会请求真实 Resource Profile。" },
  );
  useEffect(() => {
    if (scan.mode !== "api") return;
    const controller = new AbortController();
    setProfileState({ status: "loading" });
    void getResourceProfile(scan.id, resource.id, controller.signal)
      .then((profile) =>
        setProfileState(
          profile
            ? { status: "ready", profile }
            : { status: "missing", detail: "后端尚未提供该资源的 Resource Profile。" },
        ),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setProfileState({
          status: "error",
          detail: error instanceof Error ? error.message : "Resource Profile 读取失败。",
        });
      });
    return () => controller.abort();
  }, [attempt, resource.id, scan.id, scan.mode]);
  const profile = profileState.status === "ready" ? profileState.profile : null;
  const facts = resourceCardFacts(resource, profile, scan.evidence);
  const sources = evidenceSources(facts.evidence);
  const typeLabel = resource.type === "Model" ? "模型" : "数据集";
  const profileIdentity = profile?.resource_ref.resource_identity_key ?? null;
  const profileInstance = profile?.resource_ref.resource_instance_key ?? null;
  async function refreshMetadata() {
    if (!profile || refreshing) return;
    setRefreshing(true); setRefreshMessage("");
    try {
      const job = await refreshResourceProfile(scan.id, resource.id, profile.scan_ref.facts_hash, refreshKey.current);
      const item = job.items.find(value => value.resource_id === resource.id);
      if (job.status === "succeeded" && item?.observation_id) {
        setRefreshMessage(`真实元数据观测已保存 · ${item.observation_id}`);
        refreshKey.current = crypto.randomUUID();
        setAttempt(value => value + 1);
      } else {
        setRefreshMessage(`刷新未生成可信观测${item?.error_code ? `：${item.error_code}` : ""}；原状态保持不变。`);
      }
    } catch (error) {
      setRefreshMessage(error instanceof Error ? error.message : "真实元数据刷新失败，原状态保持不变。");
    } finally { setRefreshing(false); }
  }
  return (
    <article className={`og-ai-resource-card ${resource.type.toLowerCase()}`}>
      <header>
        <div className="og-ai-resource-title">
          <span className="og-resource-kind">{typeLabel}</span>
          <div>
            <h3>{resource.name}</h3>
            <code title={resource.id}>Resource ID · {resource.id}</code>
          </div>
        </div>
        <span className="og-evidence-count">{facts.evidence.length} 条 Evidence</span>
      </header>

      <dl className="og-ai-resource-facts">
        <div><dt>provider</dt><dd>{facts.provider ?? "未获取"}</dd></div>
        <div><dt>version</dt><dd>{facts.version ?? "未获取"}</dd></div>
        <div><dt>revision</dt><dd>{facts.revision ?? (facts.revisionConflicted ? "证据不足（观测冲突）" : "未获取")}</dd></div>
        <div><dt>Profile 身份键</dt><dd title={profileIdentity ?? "未获取"}>{profileIdentity ?? "未获取"}</dd></div>
        <div><dt>Profile 实例键</dt><dd title={profileInstance ?? "未获取"}>{profileInstance ?? "未获取"}</dd></div>
        <div><dt>Evidence 来源</dt><dd>{sources.length ? sources.join("、") : "证据不足"}</dd></div>
      </dl>

      <div className="og-ai-resource-verification">
        <section>
          <span>扫描观测许可</span>
          <strong>{facts.license ?? (facts.licenseConflicted ? "证据不足（观测冲突）" : "未获取")}</strong>
          <FactBadge value={facts.licenseVerification} />
        </section>
        <section>
          <span>授权状态</span>
          <FactBadge value={facts.authorization} />
        </section>
      </div>

      <div className="og-ai-resource-relation">
        <span>模型与数据集关联</span>
        <strong>未获取</strong>
        <small>当前公共 API 未提供模型—数据集事实关系；不会按名称、provider 或 URL 推断。</small>
      </div>

      <div className={`og-profile-state ${profileState.status}`}>
        <span>Resource Profile</span>
        {profileState.status === "loading" && <strong>正在只读查询…</strong>}
        {profileState.status === "ready" && <strong>已读取 · {profileState.profile.profile_id}</strong>}
        {profileState.status === "missing" && <strong>{profileState.detail}</strong>}
        {profileState.status === "error" && (
          <>
            <strong>{profileState.detail}</strong>
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>重试 Profile</button>
          </>
        )}
        {profileState.status === "ready" && scan.mode === "api" && (
          <button type="button" disabled={refreshing || !["completed", "partial"].includes(scan.status)} onClick={refreshMetadata}>
            {refreshing ? "正在请求后端观测…" : "刷新真实元数据"}
          </button>
        )}
        {refreshMessage && <small role={refreshMessage.includes("已保存") ? "status" : "alert"}>{refreshMessage}</small>}
      </div>

      <div className="og-profile-observations">
        <span>元数据观测</span>
        {!profile?.metadata_observations.length ? <strong>未获取；不会根据名称、Logo、provider 或 URL 推断。</strong> :
          profile.metadata_observations.map(observation => <details key={observation.observation_id}>
            <summary><code>{observation.observation_id}</code><FactBadge value={observation.verification_status} /></summary>
            <dl>
              <div><dt>provider</dt><dd>{observation.provider}</dd></div>
              <div><dt>requested revision</dt><dd>{observation.requested_revision ?? "未获取"}</dd></div>
              <div><dt>resolved revision</dt><dd>{observation.resolved_revision ?? "未获取"}</dd></div>
              <div><dt>来源</dt><dd>{observation.source_url}</dd></div>
              <div><dt>观测时间</dt><dd>{observation.fetched_at}</dd></div>
              {observation.fields.map(field => <div key={`${observation.observation_id}:${field.name}:${field.locator}`}><dt>{field.name}</dt><dd>{field.value ?? "未获取"} <FactBadge value={field.verification_status} /></dd></div>)}
            </dl>
            {!!observation.coverage_gaps.length && <p>证据缺口：{observation.coverage_gaps.join("；")}</p>}
          </details>)}
      </div>

      <div className="og-ai-resource-missing">
        <span>缺失信息</span>
        <div>{facts.missing.map((item) => <em key={item}>{item}</em>)}</div>
      </div>

      <footer>
        <p>
          {facts.missingEvidenceIds.length
            ? `${facts.missingEvidenceIds.length} 个 Evidence 引用尚未取得原文。`
            : facts.evidence.length
              ? "Evidence 仅证明扫描观测，不自动证明授权或合规。"
              : "当前资源没有可读取 Evidence，结论保持证据不足。"}
        </p>
        <button type="button" onClick={onEvidence}>查看资源与 Evidence</button>
      </footer>
    </article>
  );
}
