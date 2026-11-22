import { useState } from "react";
import type { Scan, EvidenceKind } from "../types/domain";
import { factVerificationLabels } from "../types/domain";
import type { DependencyEvidenceRef, DependencySource } from "../services/dependencyEvidence";
import { safeUrl } from "../services/model";
import { ActionButton, copyText, Empty, useNotice } from "./ui";
const labels: Record<EvidenceKind, string> = {
  code: "项目代码",
  license: "许可原文",
  rule: "判断依据",
};
export const dependencyEvidenceSourceLabels: Record<DependencySource, string> = {
  manifest: "Manifest",
  lock: "Lock",
  sbom: "SBOM",
  unknown: "来源未定",
};

type ScanReaderProps = { scan: Scan; ids: string[]; initialId?: string };
type ReferenceReaderProps = { references: readonly DependencyEvidenceRef[]; initialId?: string };

export function EvidenceReader(props: ScanReaderProps | ReferenceReaderProps) {
  return "references" in props ? <ReferenceEvidenceReader {...props} /> : <ScanEvidenceReader {...props} />;
}

function ReferenceEvidenceReader({ references, initialId }: ReferenceReaderProps) {
  const [selected, setSelected] = useState(initialId ?? "");
  const notify = useNotice();
  const evidence = references.find(item => item.evidence_id === selected) ?? references[0];
  if (!evidence) return <p className="og-muted">本次扫描未提供可展示的证据。</p>;
  const { file_path: path, locator, source_sha256: sha, evidence_id: id, producer } = evidence;
  const lines = evidence.start_line === null ? null
    : evidence.end_line !== null && evidence.end_line !== evidence.start_line
      ? `第 ${evidence.start_line}–${evidence.end_line} 行` : `第 ${evidence.start_line} 行`;
  return <div className="og-evidence og-dependency-evidence-reader">
    {references.length > 1 && <label className="og-field">
      选择依赖证据
      <select value={id} onChange={event => setSelected(event.target.value)}>
        {references.map((entry, index) => <option key={entry.evidence_id} value={entry.evidence_id}>
          {index + 1}. {entry.file_path ?? entry.evidence_id} · {dependencyEvidenceSourceLabels[entry.source]}
        </option>)}
      </select>
    </label>}
    <dl className="og-meta og-dependency-evidence-meta">
      <dt>来源类型</dt><dd>{dependencyEvidenceSourceLabels[evidence.source]}</dd>
      <dt>核验状态</dt><dd>{factVerificationLabels[evidence.verification_status]}</dd>
      <dt>原始文件路径</dt><dd>{path === null ? "未提供" : <code>{path}</code>}{lines && <small>{lines}</small>}</dd>
      {locator !== null && locator !== path && <><dt>记录定位</dt><dd><code>{locator}</code></dd></>}
      <dt>producer</dt><dd>{producer.name} <small>{producer.version} · {producer.type}</small></dd>
      <dt>Evidence ID</dt><dd><code>{id}</code></dd>
      <dt>SHA-256</dt><dd>{sha === null ? "未提供原文件哈希" : <code>{sha}</code>}</dd>
    </dl>
    <div className="og-actions">
      <ActionButton kind="copy" type="button" onClick={() => void copyText(id, notify)}>复制 Evidence ID</ActionButton>
      {sha !== null && <ActionButton kind="copy" type="button" onClick={() => void copyText(sha, notify)}>复制 SHA-256</ActionButton>}
    </div>
  </div>;
}

function ScanEvidenceReader({
  scan,
  ids,
  initialId,
}: ScanReaderProps) {
  const initial = scan.evidence.find((e) => e.id === initialId);
  const [kind, setKind] = useState<EvidenceKind>(initial?.kind ?? "code");
  const [selected, setSelected] = useState(initialId ?? "");
  const notify = useNotice();
  const missing = ids.filter((id) => !scan.evidence.some((e) => e.id === id));
  const entries = scan.evidence.filter(
    (e) => ids.includes(e.id) && e.kind === kind,
  );
  const missingSelection =
    !!selected &&
    ids.includes(selected) &&
    !scan.evidence.some((e) => e.id === selected);
  const evidence = missingSelection
    ? undefined
    : (entries.find((e) => e.id === selected) ?? entries[0]);
  const sourceUrl = safeUrl(evidence?.url);
  return (
    <div className="og-evidence">
      <div className="og-tabs" aria-label="证据分类">
        {Object.entries(labels).map(([k, label]) => (
          <button
            type="button"
            key={k}
            aria-pressed={kind === k}
            onClick={() => {
              setKind(k as EvidenceKind);
              setSelected("");
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {missing.length > 0 && (
        <p className="og-warning">以下证据待补充：{missing.join("、")}</p>
      )}
      {entries.length > 1 && (
        <label className="og-field">
          选择证据
          <select
            aria-label="选择证据"
            value={evidence?.id ?? ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            {entries.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {!evidence ? (
        <Empty
          title="证据待补充"
          detail="后端尚未提供此类别的原文或关联信息，前端不补造依据。"
        />
      ) : (
        <>
          <div className="og-evidence-meta">
            <strong>{evidence.label}</strong>
            <span>
              {evidence.path ?? evidence.url ?? "未提供文件位置"}
              {evidence.startLine
                ? " · 第 " + evidence.startLine + " 行起"
                : ""}
            </span>
            <small>
              来源：{evidence.source} · {evidence.id}
            </small>
          </div>
          {evidence.text === null ? (
            <Empty
              title="原文待补充"
              detail="目前仅有引用位置，没有可展示的原文。"
            />
          ) : (
            <pre aria-label="证据原文">
              <code>
                {evidence.text.split("\n").map((line, i) => {
                  const n = (evidence.startLine ?? 1) + i;
                  return (
                    <span
                      key={i}
                      className={
                        evidence.highlightLines?.includes(n)
                          ? "og-code-line highlighted"
                          : "og-code-line"
                      }
                    >
                      <b aria-hidden="true">{n}</b>
                      <span>{line || " "}</span>
                    </span>
                  );
                })}
              </code>
            </pre>
          )}
          <div className="og-actions">
            <ActionButton kind="copy"
              type="button"
              onClick={() =>
                void copyText(
                  [
                    scan.id,
                    evidence.id,
                    evidence.path ?? "",
                    evidence.text ?? "原文待补充",
                  ].join("\n"),
                  notify,
                )
              }
            >
              复制引用
            </ActionButton>
            {sourceUrl ? (
              <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                打开原始来源 ↗
              </a>
            ) : (
              <span className="og-muted">未提供安全的来源 URL</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
