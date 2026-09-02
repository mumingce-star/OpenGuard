import type { Resource, Risk } from '../types/domain';

export const risks: Risk[] = [
  { id: 'RISK-001', title: '发布目录缺少 NOTICE 文件', severity: 'critical', resource: 'transformers@4.52.0', license: 'Apache-2.0', evidenceCount: 4, confidence: 96, status: '待处理', conclusion: '项目分发了 Apache-2.0 组件，但发布目录中未发现 NOTICE 文件。', remediation: '将上游 NOTICE 内容合并至项目根目录的 NOTICE，并在发布产物中保留许可证与版权声明。' },
  { id: 'RISK-002', title: '模型卡使用范围需要人工复核', severity: 'high', resource: 'Qwen3-8B', license: 'Qwen Research', evidenceCount: 3, confidence: 88, status: '复核中', conclusion: '模型卡中包含用途限制条款，当前发布目标可能需要额外确认。', remediation: '由项目负责人复核目标用途，并在 README 的模型来源章节中补充适用范围与限制。' },
  { id: 'RISK-003', title: '数据集来源声明不完整', severity: 'medium', resource: 'OpenData-CN', license: 'CC-BY-4.0', evidenceCount: 2, confidence: 91, status: '待处理', conclusion: '数据集被代码引用，但 THIRD_PARTY_NOTICES 中没有对应署名。', remediation: '补充数据集名称、版本、来源链接、许可协议及作者署名。' },
  { id: 'RISK-004', title: 'API 服务条款链接未固定版本', severity: 'low', resource: 'Vector API', license: 'Terms of Service', evidenceCount: 1, confidence: 84, status: '已处理', conclusion: '服务条款仅引用动态网页，无法确认扫描时对应版本。', remediation: '记录扫描日期、条款版本和归档链接，作为发布审计依据。' },
];

export const resources: Resource[] = [
  { name: 'transformers', type: 'Package', version: '4.52.0', origin: 'PyPI', license: 'Apache-2.0', risk: 'critical', evidence: 4 },
  { name: 'Qwen3-8B', type: 'Model', version: '8B-Instruct', origin: 'Hugging Face', license: '待复核', risk: 'high', evidence: 3 },
  { name: 'OpenData-CN', type: 'Dataset', version: '2026.06', origin: 'ModelScope', license: 'CC-BY-4.0', risk: 'medium', evidence: 2 },
  { name: 'fastapi', type: 'Package', version: '0.116.1', origin: 'PyPI', license: 'MIT', risk: 'safe', evidence: 2 },
  { name: 'Vector Search API', type: 'API', version: 'v2', origin: 'api.vector.dev', license: '服务条款', risk: 'low', evidence: 1 },
  { name: 'Ollama', type: 'Service', version: '0.11.4', origin: 'GitHub', license: 'MIT', risk: 'safe', evidence: 2 },
  { name: 'security-grid.svg', type: 'Asset', version: 'local', origin: 'src/assets', license: '原创', risk: 'safe', evidence: 1 },
];

export const stages = ['获取仓库', '分析项目结构', '识别第三方资源', '许可证标准化', '规则合规检查', 'AI 风险解释', '生成合规报告'];

export const discoveries = [
  { type: 'PACKAGE', title: '发现依赖 transformers', detail: 'version 4.52.0 · PyPI', tone: 'violet' },
  { type: 'MODEL', title: '识别模型 Qwen3-8B', detail: 'Hugging Face Model Card', tone: 'cyan' },
  { type: 'LICENSE', title: '许可证完成标准化', detail: 'Apache License 2.0', tone: 'green' },
  { type: 'RISK', title: '发现高优先级风险', detail: 'NOTICE 文件缺失', tone: 'red' },
  { type: 'DATASET', title: '发现数据集引用', detail: 'OpenData-CN · CC-BY-4.0', tone: 'blue' },
  { type: 'AI', title: '完成风险解释', detail: '4 条建议等待人工复核', tone: 'violet' },
  { type: 'REPORT', title: '报告生成完成', detail: 'JSON 快照可导出', tone: 'green' },
];
