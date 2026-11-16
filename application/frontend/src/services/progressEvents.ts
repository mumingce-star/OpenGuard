import type { ScanProgressEvents } from "../types/domain";
const phases = ["ingestion","inventory","scan","normalize","rules","ai_assist","report"];
const states = ["start","end","completed","partial","failed","cancelled"];
export function parseProgressEvents(value: unknown, scanId: string): ScanProgressEvents {
  const fail = (): never => { throw new Error("阶段记录与当前任务不一致或格式无效。"); };
  if (!value || typeof value !== "object" || Array.isArray(value)) return fail();
  const raw = value as ScanProgressEvents;
  if (Object.keys(raw).some(key=>!["events","recording_complete","scan_id","schema_version","terminal_status","source","project_name"].includes(key)) || raw.schema_version !== "openguard.progress-events/1" || raw.scan_id !== scanId || !["queued","running","completed","partial","failed","cancelled"].includes(raw.terminal_status) || typeof raw.recording_complete !== "boolean" || !Array.isArray(raw.events) || raw.events.length>64) return fail();
  if((raw.source != null && typeof raw.source !== "string") || (raw.project_name != null && typeof raw.project_name !== "string"))return fail();
  let phase = -1, percent = 0, at = -Infinity;
  const opened = new Set<string>(), closed = new Set<string>();
  raw.events.forEach((event, i) => {
    if (!event || typeof event !== "object" || Object.keys(event).sort().join(",") !== "observed_at,percent,phase,sequence,state" || event.sequence !== i+1 || !phases.includes(event.phase) || !states.includes(event.state) || !Number.isInteger(event.percent) || event.percent<percent || event.percent>100 || typeof event.observed_at !== "string" || !Number.isFinite(Date.parse(event.observed_at)) || Date.parse(event.observed_at)<at) return fail();
    const next = phases.indexOf(event.phase);
    if (next<phase) return fail();
    if (event.state==="start") { if(opened.has(event.phase)) return fail(); opened.add(event.phase); }
    else if(event.state==="end") { if(!opened.has(event.phase) || closed.has(event.phase)) return fail(); closed.add(event.phase); }
    else if(i !== raw.events.length-1 || !opened.has(event.phase)) return fail();
    phase=next; percent=event.percent; at=Date.parse(event.observed_at);
  });
  if(raw.recording_complete && (raw.terminal_status!=="completed" || raw.events.at(-1)?.state!=="completed" || phases.filter(p=>p!=="ai_assist").some(p=>!closed.has(p))))return fail();
  return raw;
}
