import { ApiError } from './scans';

// Explicit build capability for the independent review preview, not an authorization check.
export const readOnlyPreview = import.meta.env.VITE_OPENGUARD_READ_ONLY_PREVIEW === 'true';
export const aiLoopOnly = import.meta.env.VITE_OPENGUARD_AI_LOOP_ONLY === 'true';
export const readOnlyNotice = '只读预览：可查看结果、试填用途，不能保存或重新评估。';
export type SavedIdentity = { scan: string; id: string; version: number };
export type FailureStage = 'submit' | 'read' | 'chat-submit' | 'chat-clear';
export function assessmentFailure(stage: FailureStage, cause: unknown, saved?: SavedIdentity) {
  const rejected = cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.status !== 408;
  const message = stage === 'submit'
    ? rejected ? '评估提交未被接受；原结果和草稿保留。请核对当前运行环境是否允许提交。'
      : '提交结果尚未确认，可能已被服务接收；原结果和草稿保留。请先读取评估状态，不要重复提交。'
    : stage === 'chat-submit' ? '问答提交未完成；请先读取问答记录确认状态，避免重复发送。'
    : stage === 'chat-clear' ? '清空结果尚未确认；请先读取问答记录。'
    : saved ? `评估第 ${saved.version} 版已保存，但新结果暂未完整读取；当前草稿保留，可重新读取。`
    : cause instanceof ApiError && cause.status === 404 ? '所选评估暂不可读取；原扫描和历史结果保留。'
    : '读取未完成；仍可查看已读取的结果，请稍后重新读取。';
  // Keep the original error, including HTTP status/code, out of ordinary user copy.
  return { stage, cause, saved, message };
}
