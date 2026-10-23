import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ActionButton, Checkbox, DownloadControl, FlipCard, HelpTip, LoadingDots, Panel, SearchGlyph, SegmentedControl } from './components/ui';
import './styles/index.css';
import './styles/workspace.css';

function Samples() {
  const [checked, setChecked] = useState(false);
  const [input, setInput] = useState('github');
  const [file, setFile] = useState('');
  const [copyState, setCopyState] = useState('');
  return <main className="og-app"><div className="og-ui-samples">
    <header><p className="og-eyebrow">OPENGUARD / INTERACTION DESIGN</p><h1>更精致，也更有回应。</h1><p>独立 UI 交互样板 · 没有扫描或评估数据，不向业务 API 提交请求。</p><a href="/">查看升级后的作品首页 ↗</a></header>
    <div className="og-ui-sample-grid">
      <Panel title="01 / 有迹可循的选择" caption="描边勾选 · 紧凑多选 · 原生键盘操作">
        <Checkbox checked={checked} onChange={event => setChecked(event.target.checked)}>选择这项设计样板</Checkbox>
        <Checkbox compact defaultChecked>紧凑列表：已选中</Checkbox><Checkbox disabled>暂不可用的操作</Checkbox>
        <SegmentedControl label="样板输入方式" value={input} onChange={setInput} options={[{ value: 'github', label: 'GitHub 仓库' }, { value: 'zip', label: '上传 ZIP' }]} />
      </Panel>
      <Panel title="02 / 更专注的输入" caption="浮动标签 · 聚焦描边 · 清晰的输入区域">
        <label className="og-field og-floating-field"><input type="url" placeholder="https://github.com/owner/repository" /><span>公开仓库地址</span></label>
        <label className="og-field og-search-field"><span>搜索样板</span><span className="og-search-control"><SearchGlyph /><input type="search" placeholder="资源、版本、来源…" /></span></label>
      </Panel>
      <Panel title="03 / 每个动作都有反馈" caption="青色主操作 · 飞机发送 · 紫色复制 · 播放入口">
        <div className="og-actions"><ActionButton>主要操作</ActionButton><ActionButton kind="send">提交材料</ActionButton><ActionButton kind="copy" onClick={() => void navigator.clipboard.writeText('OpenGuard UI sample').then(() => setCopyState('已复制样板文字。')).catch(() => setCopyState('复制受限，请使用页面文字手动复制。'))}>复制引用</ActionButton><ActionButton kind="play">演示入口</ActionButton><ActionButton disabled>暂不可用</ActionButton><ActionButton kind="send" disabled aria-busy>请求处理中</ActionButton></div><p role="status">{copyState}</p>
      </Panel>
      <Panel title="04 / 下载有真实状态" caption="胶囊轮廓 · 圆形图标分区 · 忙碌、错误、重试">
        <div className="og-actions"><DownloadControl href="/ui-sample.txt" filename="openguard-ui-sample.txt" format="text/plain">下载样板文本</DownloadControl><DownloadControl disabled href="/ui-sample.txt">暂不可下载</DownloadControl></div><p>附件是静态样板文字，不含扫描结果。只有取得附件后才提示已发起下载。</p>
      </Panel>
      <Panel title="05 / 文件已选择才有下一步" caption="这是本地文件选择样板，不上传文件">
        <div className="og-sample-upload"><span aria-hidden="true">⇧</span><strong>{file || '选择一个 ZIP 查看文件状态'}</strong><input aria-label="样板 ZIP" type="file" accept=".zip" onChange={event => setFile(event.target.files?.[0]?.name ?? '')} />{file && <ActionButton kind="remove" onClick={() => setFile('')}>移除文件</ActionButton>}</div>
      </Panel>
      <Panel title="06 / 适量的提示与等待" caption="聚焦、悬停、点击都能查看辅助说明">
        <p>来源 Hash <HelpTip label="样板 Hash 说明">正式 Hash 由后端返回。此处仅说明控件交互，没有生成业务 Hash。</HelpTip></p><LoadingDots label="加载器设计样板" detail="此处没有业务请求，实际页面仅在读取时显示。" />
      </Panel>
      <Panel title="07 / 理解信息的边界" caption="点击翻转 · 键盘可操作 · 减少动态效果时直接切换">
        <FlipCard index="01" title="证据优先" summary="选择一条线索，查看它的来源。">正式结论、AI 建议和草稿保持各自来源；未知和待核验状态始终可见。</FlipCard>
      </Panel>
      <Panel title="08 / 表单也有层次" caption="内凹编辑区 · 边缘高光 · 稳定的文字对比度">
        <div className="og-p2-panel"><form onSubmit={event => event.preventDefault()}><fieldset><legend>编辑区域设计样板</legend><label>来源说明<textarea placeholder="输入样板说明，不会保存…" /></label><ActionButton kind="send" type="submit">体验按压反馈</ActionButton></fieldset></form></div>
      </Panel>
    </div>
  </div></main>;
}
createRoot(document.getElementById('root')!).render(<Samples />);
