import { GlowCursor } from "../components/GlowCursor";
import { ParticleText } from "../components/ParticleText";
import { HeroBackground } from "../components/HeroBackground";
import { ActionButton, ArrowGlyph, FlipCard } from "../components/ui";
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
      <div className="landing-intro">
        <HeroBackground />
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
          <div className="hero-badge">
            <span /> AI 开源合规与溯源助手
          </div>
          <ParticleText text="OpenGuard" />
          <p className="hero-copy">
            看清资源与风险，<strong>让结论有据可循。</strong>
          </p>
          <p className="hero-detail">从项目扫描到正式评估，沿着证据找到每一步依据。</p>
          <div className="hero-actions">
            <button className="primary-button og-arrow-button" type="button" onClick={onEnter}>
              <span>开始安全扫描</span><ArrowGlyph />
            </button>
            <ActionButton kind="play" className="secondary-button" onClick={onDemo}>
              加载演示项目
            </ActionButton>
          </div>
          <div className="hero-meta" aria-label="产品特性">
            <span>01 / 资源发现</span>
            <span>02 / 许可证判断</span>
            <span>03 / AI 风险解释</span>
            <span>04 / 合规报告</span>
          </div>
        </section>
      </div>

      <section id="capability" className="recognition-slice">
        <div>
          <p className="eyebrow">EXPLAINABLE BY DESIGN</p>
          <h2>从一条线索，<br />找到它的依据。</h2>
          <p className="section-copy">
            资源、许可证声明与核查线索保持来源关联。打开 Evidence，继续核对文件、字段和上下文。
          </p>
        </div>
        <div className="signal-card og-glass-card">
          <span className="signal-label">示意 · 证据追溯路径</span>
          <div className="signal-path">
            <span>requirements.txt:2</span>
            <i>→</i>
            <span>transformers</span>
            <i>→</i>
            <span>许可证声明</span>
            <i>→</i>
            <strong>待核验</strong>
          </div>
          <div className="source-row">
            <span className="source scanner">扫描事实</span>
            <span className="source rule">规则判断</span>
            <span className="source ai">AI 推断</span>
          </div>
        </div>
      </section>

      <section className="og-authority-section" aria-label="三个来源各司其职">
        <div className="workflow-title"><p className="eyebrow">THREE SOURCES / ONE EVIDENCE CHAIN</p><h2>理解每种信息，也理解它的边界。</h2></div>
        <div className="og-flip-grid">
          <FlipCard index="01" title="扫描事实" summary="从资源身份、版本和原文位置开始。">扫描记录描述已观测的事实；未获取的信息仍为未知，部分扫描不会被解释为资源已删除。</FlipCard>
          <FlipCard index="02" title="规则与正式评估" summary="判断有出处，版本有绑定。">Formal Assessment 是正式评估来源。任务完成和用户声明都不会自动改变许可、授权或义务履行结论。</FlipCard>
          <FlipCard index="03" title="AI 辅助解释" summary="把线索讲清楚，帮助下一步核查。">AI 内容用于辅助理解和行动建议；保留证据缺口与待核验状态，不进入 Formal Conclusion。</FlipCard>
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

      <section className="og-brand-story" aria-labelledby="brand-story-title">
        <article className="og-brand-story-card">
          <div className="og-brand-story-copy">
            <p className="eyebrow">READY TO EXPLORE</p>
            <h2 id="brand-story-title">一眼看见结论，也能一路追到证据。</h2>
            <p>未知仍是未知，待核验不会被包装成已核验。</p>
          </div>
            <button className="secondary-button og-arrow-button" type="button" onClick={onEnter}>
              <span>进入可追溯工作台</span><ArrowGlyph />
            </button>
        </article>
      </section>
    </main>
  );
}
