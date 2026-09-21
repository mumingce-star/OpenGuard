import { GlowCursor } from "../components/GlowCursor";
import { ParticleText } from "../components/ParticleText";
export function Brand({
  onClick,
  compact = false,
}: {
  onClick: () => void;
  compact?: boolean;
}) {
  return (
    <button
      className={`brand ${compact ? "brand-compact" : ""}`}
      type="button"
      onClick={onClick}
      aria-label="返回 OpenGuard 首页"
    >
      <span className="brand-mark">OG</span>
      {!compact && <span>OpenGuard</span>}
    </button>
  );
}

export function Landing({
  onEnter,
  onDemo,
}: {
  onEnter: () => void;
  onDemo: () => void;
}) {
  return (
    <main className="landing-shell">
      <GlowCursor />
      <header className="landing-nav">
        <Brand
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        />
        <nav aria-label="首页导航">
          <a href="#capability">核心能力</a>
          <a href="#workflow">工作流</a>
          <button className="nav-cta" type="button" onClick={onEnter}>
            进入工作台
          </button>
        </nav>
      </header>

      <section className="hero-section">
        <div className="ambient-grid" aria-hidden="true" />
        <div className="hero-badge">
          <span /> AI 开源合规与溯源助手
        </div>
        <ParticleText text="OpenGuard" />
        <p className="hero-copy">
          让每一个风险，都有证据可循；让每一次发布，都更有底气。
        </p>
        <div className="hero-actions">
          <button className="primary-button" type="button" onClick={onEnter}>
            开始安全扫描 <span>↗</span>
          </button>
          <button className="secondary-button" type="button" onClick={onDemo}>
            加载演示项目
          </button>
        </div>
        <div className="hero-meta" aria-label="产品特性">
          <span>01 / 资源发现</span>
          <span>02 / 许可证判断</span>
          <span>03 / AI 风险解释</span>
          <span>04 / 合规报告</span>
        </div>
      </section>

      <section id="capability" className="recognition-slice">
        <div>
          <p className="eyebrow">EXPLAINABLE BY DESIGN</p>
          <h2>
            不止告诉你“有风险”，
            <br />
            更告诉你“为什么”。
          </h2>
          <p className="section-copy">
            扫描器发现事实，规则引擎给出判断，AI
            负责解释与整改。三个来源清晰分层，每个结论都能回到文件、字段与许可依据。
          </p>
        </div>
        <div className="signal-card">
          <span className="signal-label">演示证据链 · RISK-001</span>
          <div className="signal-path">
            <span>requirements.txt:2</span>
            <i>→</i>
            <span>transformers</span>
            <i>→</i>
            <span>Apache-2.0</span>
            <i>→</i>
            <strong>分发义务待核对</strong>
          </div>
          <div className="source-row">
            <span className="source scanner">扫描事实</span>
            <span className="source rule">规则判断</span>
            <span className="source ai">AI 推断</span>
          </div>
        </div>
      </section>

      <section id="workflow" className="workflow-section">
        <div className="workflow-title">
          <p className="eyebrow">ONE TRACEABLE FLOW</p>
          <h2>从仓库到报告，一条证据链跑到底。</h2>
        </div>
        <div className="workflow-grid">
          {[
            "输入仓库 / ZIP",
            "七阶段智能扫描",
            "定位风险与证据",
            "导出合规报告",
          ].map((item, index) => (
            <div className="workflow-card" key={item}>
              <span>0{index + 1}</span>
              <h3>{item}</h3>
              <p>
                {
                  [
                    "公开仓库或 ZIP 输入，安全检查由后端负责。",
                    "识别包、模型、数据集、API 与服务。",
                    "查看规则结论、代码位置与整改建议。",
                    "生成可复核、可交付的资源与风险清单。",
                  ][index]
                }
              </p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
