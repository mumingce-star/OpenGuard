export type ScanDiagnostic = {
  code: string;
  message: string;
  stage?: string;
  tool?: string | null;
  recoverable?: boolean;
};

export type ProductDiagnostic = {
  title: string;
  detail: string;
};

export type ProjectFactCard = {
  label: string;
  value: string;
  detail?: string;
  note: string;
};

export type ProjectSummaryView = {
  conclusion: string;
  facts: ProjectFactCard[];
};

export function presentDiagnostic(diagnostic: ScanDiagnostic): ProductDiagnostic {
  if (diagnostic.code === 'python_dependency_scan_partial') {
    const reason = diagnostic.message.match(/^Python dependency scan was partial: ([a-z_]+) at /)?.[1];
    const location = diagnostic.message.match(/\bat\s+([^:\s]+):(\d+)/i);
    const prefix = location ? `${location[1]} 第 ${location[2]} 行` : '';
    let detail = `${prefix}该依赖声明当前未被完整解析；具体技术原因请查看下方技术诊断。`;
    if (reason === 'requirement_editable_unsupported') {
      detail = `${prefix}包含当前暂不支持的 editable 依赖声明；相关依赖可能未完整识别。`;
    } else if (reason === 'dependency_multiple_constraints') {
      detail = `${prefix}存在多个依赖约束；相关依赖结果需要进一步核对。`;
    }
    return {
      title: 'Python 依赖扫描不完整',
      detail,
    };
  }

  if (diagnostic.code === 'git_scan_coverage_partial') {
    const counts = diagnostic.message.match(
      /仓库共\s*(\d+)\s*个条目.*?读取\s*(\d+)\s*个文件；\s*(\d+)\s*个条目未扫描/,
    );
    return {
      title: '仓库覆盖不完整',
      detail: counts
        ? `仓库共 ${counts[1]} 个条目，本次读取 ${counts[2]} 个文件，还有 ${counts[3]} 个条目未扫描。`
        : '仓库中仍有部分条目未被本次有界扫描覆盖。',
    };
  }

  if (diagnostic.code === 'scan_incomplete') {
    return {
      title: '报告基于部分扫描结果生成',
      detail: '当前已有结果可以查看，但不能据此认为整个仓库已经完整覆盖。',
    };
  }

  const stage = diagnostic.stage ? `“${diagnostic.stage}”阶段` : '扫描过程中';
  return {
    title: '存在额外覆盖限制',
    detail: `${stage}记录到需要进一步核对的问题；技术原文保留在下方诊断详情中。`,
  };
}

function projectFact(line: string): ProjectFactCard | null {
  const root = line.match(/^根目录许可文件记录到：(.+?)。/);
  if (root) {
    return {
      label: '许可证线索',
      value: root[1],
      note: '仅为根目录文件级许可观察；适用关系仍待核验，不自动适用于第三方依赖。',
    };
  }

  if (line.startsWith('已有根目录许可文件观察')) {
    return {
      label: '许可证线索',
      value: '已发现根目录许可线索',
      note: '当前记录尚不能确认具体授权关系。',
    };
  }

  if (line.startsWith('本次结果尚未建立根目录许可文件观察')) {
    return {
      label: '许可证线索',
      value: '暂未建立根目录许可观察',
      note: '这不等于仓库不存在许可证。',
    };
  }

  const components = line.match(/^组件共(\d+)条：(.+?)。此分类/);
  if (components) {
    return {
      label: '组件声明',
      value: `${components[1]} 条组件记录`,
      detail: components[2],
      note: '这里反映声明字段或扫描位置，不代表最终使用或交付范围已经核验。',
    };
  }

  if (line.startsWith('本次未记录组件')) {
    return {
      label: '组件声明',
      value: '本次未记录组件',
      note: '不能据此断言项目没有第三方依赖。',
    };
  }

  const ai = line.match(/^另有(\d+)条AI资产记录/);
  if (ai) {
    return {
      label: 'AI 资产',
      value: `${ai[1]} 条 AI 资产记录`,
      note: 'AI 资产仍需要独立核对授权条件。',
    };
  }

  if (line.startsWith('本次未识别到AI资产记录')) {
    return {
      label: 'AI 资产',
      value: '本次未识别到 AI 资产记录',
      note: '这不等于项目一定不存在 AI 资产。',
    };
  }

  return null;
}

export function presentProjectSummary(summary: string): ProjectSummaryView {
  const blocks = summary.split(/\n\n+/).map(block => block.trim()).filter(Boolean);
  if (blocks.length < 2) {
    return { conclusion: summary.trim(), facts: [] };
  }

  const factLines = blocks[0].split('\n').map(line => line.trim()).filter(Boolean);
  const facts = factLines.map(projectFact).filter((item): item is ProjectFactCard => item !== null);

  if (!facts.length) {
    return { conclusion: summary.trim(), facts: [] };
  }

  return {
    conclusion: blocks.slice(1).join('\n\n').trim(),
    facts,
  };
}
