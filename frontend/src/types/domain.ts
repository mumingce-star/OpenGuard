export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type SourceType = 'scanner' | 'rule_engine' | 'ai_inference';

export type Risk = {
  id: string;
  title: string;
  severity: Severity;
  resource: string;
  license: string;
  evidenceCount: number;
  confidence: number;
  status: '待处理' | '复核中' | '已处理';
  conclusion: string;
  remediation: string;
};

export type Resource = {
  name: string;
  type: 'Package' | 'Model' | 'Dataset' | 'API' | 'Service' | 'Asset';
  version: string;
  origin: string;
  license: string;
  risk: Severity | 'safe';
  evidence: number;
};
