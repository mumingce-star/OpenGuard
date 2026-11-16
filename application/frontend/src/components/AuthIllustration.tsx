export function AuthIllustration({ register = false }: { register?: boolean }) {
  return (
    <svg
      className="auth-illustration-svg"
      viewBox="0 0 500 360"
      fill="none"
      role="img"
      aria-label="OpenGuard 开源合规取证与基线可复核架构示意图"
    >
      <defs>
        <radialGradient id="og-auth-halo" cx="50%" cy="42%" r="45%">
          <stop offset="0%" stopColor="#2f8566" stopOpacity="0.16" />
          <stop offset="65%" stopColor="#19614b" stopOpacity="0.04" />
          <stop offset="100%" stopColor="#eff5f1" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="og-shield-grad" x1="216" y1="106" x2="284" y2="192" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#f1f7f3" />
        </linearGradient>
        <filter id="og-card-shadow" x="0%" y="0%" width="100%" height="125%">
          <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#134b3a" floodOpacity="0.07" />
        </filter>
      </defs>

      {/* Ambient radial light & concentric orbital rings centered on (250, 146) */}
      <circle cx="250" cy="146" r="185" fill="url(#og-auth-halo)" />
      <circle cx="250" cy="146" r="168" stroke="#c7dcd0" strokeWidth="1" strokeDasharray="3 5" />
      <circle cx="250" cy="146" r="122" stroke="#cfe2d7" strokeWidth="1" />
      <circle cx="250" cy="146" r="76" stroke="#b9d4c4" strokeWidth="1" strokeDasharray="2 4" />

      {/* Precision blueprint corner crosshairs aligned to outer 16..484 frame */}
      <g stroke="#9bb9a8" strokeWidth="1.2" strokeLinecap="round">
        <path d="M16 14v8M12 18h8" />
        <path d="M484 14v8M480 18h8" />
        <path d="M16 346v8M12 350h8" />
        <path d="M484 346v8M480 350h8" />
      </g>

      {/* Symmetric topological orthogonal + Bezier connectors */}
      <g strokeLinecap="round">
        <path d="M250 48V100" stroke="#19614b" strokeWidth="1.5" />
        <path d="M168 146H204" stroke="#19614b" strokeWidth="1.5" />
        <path d="M296 146H332" stroke="#b45309" strokeOpacity="0.55" strokeWidth="1.5" strokeDasharray="4 4" />
        <path d="M250 194V232" stroke="#19614b" strokeWidth="1.5" />
        <path d="M92 188C92 212 146 212 190 232" stroke="#b8d1c2" strokeWidth="1.2" />
        <path d="M408 188C408 212 354 212 310 232" stroke="#b8d1c2" strokeWidth="1.2" />
      </g>

      {/* Junction pins */}
      <circle cx="250" cy="48" r="3" fill="#ffffff" stroke="#19614b" strokeWidth="1.5" />
      <circle cx="168" cy="146" r="3" fill="#ffffff" stroke="#19614b" strokeWidth="1.5" />
      <circle cx="332" cy="146" r="3" fill="#ffffff" stroke="#d97706" strokeWidth="1.5" />
      <circle cx="250" cy="232" r="3.5" fill="#19614b" />

      {/* Top Origin Capsule: x centered at 250 */}
      <g filter="url(#og-card-shadow)">
        <rect x="112" y="14" width="276" height="34" rx="17" fill="#ffffff" stroke="#c3dad0" strokeWidth="1" />
      </g>
      <circle cx="132" cy="31" r="4" fill="#2f8566" />
      <text
        x="257"
        y="35"
        textAnchor="middle"
        fill="#111c17"
        fontSize="11"
        fontWeight="600"
        fontFamily="JetBrains Mono, SF Mono, Menlo, monospace"
      >
        {register ? '流程示意 · 独立账号空间' : '示例数据 · http-server@14.1.2'}
      </text>

      {/* Left Verification Card (x: 16..168, y: 104..188) */}
      <g filter="url(#og-card-shadow)">
        <rect x="16" y="104" width="152" height="84" rx="10" fill="#ffffff" stroke="#c7ddd1" strokeWidth="1" />
      </g>
      <circle cx="32" cy="124" r="3.5" fill="#2f8566" />
      <text x="42" y="128" fill="#111c17" fontSize="12" fontWeight="650">
        {register ? '独立账号空间' : 'LICENSE 原文'}
      </text>
      <text x="29" y="149" fill="#4f6359" fontSize="11">
        {register ? '按用户隔离扫描历史' : 'MIT · UTF-8 逐字节锚定'}
      </text>
      <rect x="29" y="160" width="126" height="18" rx="4" fill="#ecf5f0" />
      <text
        x="92"
        y="172.5"
        textAnchor="middle"
        fill="#19614b"
        fontSize="9.5"
        fontWeight="600"
        fontFamily="JetBrains Mono, SF Mono, Menlo, monospace"
      >
        {register ? '示例范围 · 账号隔离' : '示例摘要: accfc4d5'}
      </text>

      {/* Central Focal Seal: Geometric Shield & Deterministic Check Lattice */}
      <circle cx="250" cy="146" r="46" fill="#e6f2eb" stroke="#bfd7ca" strokeWidth="1" />
      <path
        d="M250 107L283 120V148C283 169 268 182 250 190C232 182 217 169 217 148V120L250 107Z"
        fill="url(#og-shield-grad)"
        stroke="#19614b"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M250 115L275 125V147C275 163 264 173 250 180C236 173 225 163 225 147V125L250 115Z"
        fill="#ecf5f0"
        stroke="#a7cbb9"
        strokeWidth="1"
      />
      <path
        d="M239 147L247 155L263 137"
        stroke="#19614b"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Right Verification Card (x: 332..484, y: 104..188) */}
      <g filter="url(#og-card-shadow)">
        <rect x="332" y="104" width="152" height="84" rx="10" fill="#ffffff" stroke="#d5e2db" strokeWidth="1" />
      </g>
      <circle cx="348" cy="124" r="3.5" fill={register ? '#2f8566' : '#d97706'} />
      <text x="358" y="128" fill="#111c17" fontSize="12" fontWeight="650">
        {register ? '固定依据绑定' : '传递依赖边界'}
      </text>
      <text x="345" y="149" fill="#4f6359" fontSize="11">
        {register ? '与旧录制入口互不混杂' : '未知项显式保留不放行'}
      </text>
      {/* Segmented coverage bar inside right card */}
      <rect x="345" y="164" width="126" height="6" rx="3" fill="#edf2ef" />
      <rect x="345" y="164" width={register ? '126' : '84'} height="6" rx="3" fill="#19614b" />
      {!register && <rect x="432" y="164" width="39" height="6" rx="3" fill="#e59a24" />}

      {/* Bottom Aligned Evidence Pipeline Card (x: 16..484, exact flush width 468px) */}
      <g filter="url(#og-card-shadow)">
        <rect x="16" y="232" width="468" height="106" rx="12" fill="#ffffff" stroke="#c7ddd1" strokeWidth="1" />
      </g>
      <text
        x="34"
        y="255"
        fill="#687a71"
        fontSize="10"
        fontWeight="600"
        letterSpacing="0.06em"
        fontFamily="JetBrains Mono, SF Mono, Menlo, monospace"
      >
        OPENGUARD 流程示意
      </text>
      <rect x="332" y="242" width="134" height="18" rx="9" fill="#ecf5f0" stroke="#c4dcd0" strokeWidth="0.8" />
      <text
        x="399"
        y="254"
        textAnchor="middle"
        fill="#19614b"
        fontSize="9.5"
        fontWeight="600"
        fontFamily="JetBrains Mono, SF Mono, Menlo, monospace"
      >
        {register ? '流程示意 · 账号隔离' : '流程示意 · r1 → r2'}
      </text>
      <line x1="34" y1="268" x2="466" y2="268" stroke="#ebf1ed" strokeWidth="1" />

      {/* 3-Node Horizontal Pipeline strictly aligned on y=294 */}
      <line x1="104" y1="294" x2="250" y2="294" stroke="#19614b" strokeWidth="1.6" />
      <line x1="250" y1="294" x2="396" y2="294" stroke="#9ec0ae" strokeWidth="1.5" strokeDasharray="4 4" />

      {/* Step 1 */}
      <circle cx="104" cy="294" r="10" fill="#19614b" />
      <text x="104" y="297.5" textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, SF Mono, Menlo, monospace">
        1
      </text>
      <text x="104" y="321" textAnchor="middle" fill="#111c17" fontSize="11.5" fontWeight="600">
        源码扫描取证
      </text>

      {/* Step 2 */}
      <circle cx="250" cy="294" r="10" fill="#19614b" />
      <text x="250" y="297.5" textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, SF Mono, Menlo, monospace">
        2
      </text>
      <text x="250" y="321" textAnchor="middle" fill="#111c17" fontSize="11.5" fontWeight="600">
        七项用途核查
      </text>

      {/* Step 3 */}
      <circle cx="396" cy="294" r="10" fill="#ecf5f0" stroke="#19614b" strokeWidth="1.8" />
      <text x="396" y="297.5" textAnchor="middle" fill="#19614b" fontSize="10" fontWeight="700" fontFamily="JetBrains Mono, SF Mono, Menlo, monospace">
        3
      </text>
      <text x="396" y="321" textAnchor="middle" fill="#41524a" fontSize="11.5" fontWeight="600">
        报告归档与智询
      </text>
    </svg>
  );
}
