# OpenGuard v2.2.0 验证记录

产品与测试基线为 `2a07d7bbe43b39cb4b8f211895f1fc5a54a77893`。里程碑只刷新五份顶层元数据、文档和文件清单。提交链和受保护树摘要见 [VERSION.json](VERSION.json)。

## TASK50 冻结产品树实测

| 门禁 | 通过／总数 |
| --- | ---: |
| `CORE_P4_PYTEST` | 324/324 |
| `TASK39_PYTEST` | 118/118 |
| `B58_PYTHON_TESTS` | 142/142 |
| `TASK41_PYTEST` | 12/12 |
| `TASK45_PYTHON_TESTS` | 92/92 |
| `CORE_AND_TASK45_NODE_TESTS` | 347/347 |
| `B58_MJS_TESTS` | 25/25（含 pnpm 5/5） |
| `TSC` | 1/1 |
| `LAUNCHER_CONFIG_CHECK` | 1/1 |
| **合计** | **1062/1062** |

九组门禁退出码均为 0，失败、错误、跳过和 IP/DNS 拒绝尝试均为 0。旧版 `action-plan/2` 补充核验为 154/154，单独计数。

原生隔离 `openguard.py self-test` 通过 37/37，退出码为 0，63 次 HTTP 交换均使用同一个临时回环端口，模型调用为 0，服务已退出。自检按 `openguard-material-claims/4` 契约检验补材前的 `UNKNOWN`、补材后的条件 `SUPPORT`、r1→r2 的影响集、历史 Result 的原字节以及评估包下载。v2.0.0 的 `/3` 断言已在当前产品树改为 v4 契约检查。

离线 Vite 构建及成品核验为 1/1。8 份 `web/` 产物共 1,258,482 字节，构建产物与冻结树逐字节一致。最大 JS 为 290,212 字节，超过 500 kB 的 chunk 告警为 0。逐文件摘要见 [RESOURCE_USAGE.md](RESOURCE_USAGE.md)。

TASK50 总验收为 1100/1100，即九组门禁 1062 项、原生自检 37 项和离线 Vite 1 项。包外原始回执位于 `output/releases/v2.2-task50/TASK50_RECEIPT.md`，SHA-256 为 `cc9545e893dd57dbedbe3f444437bcbd2527becba4a8e506bd1243d64d11f458`。同目录的 `logs/gate-02-results.json` 和 `junit/gate-02/` 记录逐组结果。

## TASK51 洁净解压复验

本轮使用本地提交的 887 个跟踪文件构建确定性 ZIP。从同一新解压树验证 886 份清单记录、运行 `openguard.py check`、检查外层及嵌套归档的禁入项、复跑原生隔离自检 37 项与上述九组 1062 项门禁。临时测试输入与运行时来自指定的本地离线依赖。复验后重新对照包内 887 个文件的提交字节及 886 份清单记录。

最终 ZIP 的身份、本轮冷验实测结果与日志摘要记录在包外的 `output/releases/v2.2.0/TASK51_RECEIPT.md`。上文的 1100/1100 来自 TASK50 独立验收。

## 历史验证

### TASK46 统一离线门禁与 TASK48 v2.0.0 冷验

| 门禁 | 通过／总数 |
| --- | ---: |
| `CORE_P4_PYTEST` | 278/278 |
| `TASK39_PYTEST` | 86/86 |
| `B58_PYTHON_TESTS` | 142/142 |
| `TASK41_PYTEST` | 12/12 |
| `TASK45_PYTHON_TESTS` | 76/76 |
| `CORE_AND_TASK45_NODE_TESTS` | 319/319 |
| `B58_MJS_TESTS` | 25/25（含 pnpm 5/5） |
| `TSC` | 1/1 |
| `LAUNCHER_CONFIG_CHECK` | 1/1 |
| **合计** | **940/940** |

上述 TASK46 门禁为 0 FAIL、0 ERROR、0 SKIP。构建与门禁的 IP/DNS 守卫记录均为 0。离线构建退出码为 0，8 份 Web 产物经逐字节校验，超过 500 kB 的 chunk 告警为 0。原始回执和 JUnit 位于包外目录 `output/competition/task46-unified-remediation/`。

TASK48 使用 880 个跟踪文件生成 v2.0.0 包，在洁净解压树核验 879 份清单及 `openguard.py check`，九组复验为 940/940。旧版包的 `self-test` 含 `material-claims/3` 断言，TASK48 当时记录为 `NOT_RUN`。原始结果见 `output/releases/v2.0.0/TASK48_RECEIPT.md`。

### TASK46 Chrome 端到端

Chrome `158.0.8127.36` 与 Playwright `1.62.1` 在独立本机 `TEST_ONLY` 环境中通过 **17/17**。四个 TEST_ONLY ZIP 实际上传扫描，覆盖 MIT 主样本的依赖证据和版本冲突、正式 Assessment、P2 r1→r2、历史 r1 固定、评估包下载及 Report V2 双版本归档。Apache-2.0、ISC 和 SPDX `-or-later` 的相关界面提示亦已验证。

记录 339 次页面请求，其中 225 次 API 请求，338 次 2xx，1 次登录会话读取未捕获响应码。观测到 0 次 4xx、0 次 5xx、0 次控制台错误、0 次外部 HTTP、0 次模型调用。Chrome 自身发出的 6 次后台 CONNECT 被回环代理拒绝，3 次非回环 IPv6 UDP 探测失败并发送 0 字节。12 张截图留在 TASK46 外部证据目录。

### TASK47B 独立 Holdout

TASK47B 在历史冻结基线 `a9081dfbf900b7a901120e611603fed5f441fbd9` 上通过 **57/57**，严重安全错误为 0。两份 npm ZIP 样本与其余单列核验共同组成 57 项。

| 分区 | 结果 |
| --- | --- |
| 主张 | 12/12。`tinyglobby@0.2.17` 的 MIT r1 三项 `UNKNOWN`，r2 三项条件 `SUPPORT`，核对 5 个原文条款区间。`lightningcss@1.32.0` 的 MPL-2.0 两版共六项 `UNKNOWN`，均有弱 Copyleft 提示。 |
| 依赖证据与报告 | 依赖证据 3/3。Report V2 1.0/1.1 共 4/4，核验同一扫描和正式 Assessment 绑定、原字节与不可变重读。 |
| 双向许可反例 | 6/6。已识别的 MIT 原文与 MPL-2.0 声明冲突得到 `SPDX_TEXT_CONFLICT`。当时的解析器尚不能识别 MPL 原文，反向保守返回 `UNKNOWN`。 |
| 安全回归 | P6 永久安全反例 10/10，补充控制 19/19。 |
| BSD-2 独立附加项 | `Pygments@2.21.0` 的真实 BSD-2-Clause 原文 3/3，位于 `APPENDIX_TEXT_ONLY`，独立于主 Holdout 分母。 |

主 Holdout 条件支持精确率和覆盖率均为 3/3，保守漏报 0。全部主张中获条件支持的比例为 3/12。进程内 ASGI 记录 87 次 HTTP 交换，0 次 4xx/5xx，IP/DNS 外联尝试和真实模型调用均为 0。原始证据在 `output/competition/task47b-v2-holdout-benchmark/`。

### 历史 P6 基准

TASK41 在父提交 `ab2c1256c4a2efb8714cc90b9f39eda0fc5fc224` 上记录 21 个 ASGI 场景、48 条去重主张、535 次交换（含重复测量）和 10/10 条永久安全负例。基准清单、执行器与报告进入 `1f4dc46aab5c494be71c518fe869787a24f679ba`。主张中观察到严重安全错误 0/48。开发集精确标签匹配 29/36，独立 Holdout 9/12，条件建议分别为 7/7 和 0/0（未产出 `SUPPORT`，精确率未定义）。两组共 10 条保守漏判，标注状态为 `SINGLE_ANNOTATOR_FROZEN_PENDING_SECOND_HUMAN_REVIEW`。历史离线门禁为 744/744，原证据与标签边界见 [P6 实测报告](application/benchmarks/P6_BENCHMARK_REPORT.md)。

## 固定样例合规例外

Owner 仅批准固定 `samples/http-server.bundle` 内的下列六个台账项，外层包及其他嵌套内容继续适用禁入扫描。Bundle SHA-256 `b4d28764503ce135702d948878d8604495fd0addf38c7a070892e93d038c714b`。两份 PEM 是上游公开单元测试夹具，均非真实私有凭据。另四份为同一 MIT 上游快照公开示例及文档图片，未发现独立排除声明。例外绑定来源、精确相对路径与文件 SHA-256。

| 上游快照 | 包内精确路径 | SHA-256 | 用途 |
|---|---|---|---|
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `test/fixtures/https/agent2-cert.pem` | `86cb2e5062f9c132ba293ba1900b6499b92970126651ce78132a2f7dec5667de` | 上游公开 TLS 单元测试证书 |
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `test/fixtures/https/agent2-key.pem` | `1e67ba403f19109a90f974c5a2f2e7513dfe07bca6d899374afd651952a010f8` | 上游公开 TLS 单元测试私钥 |
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `public/img/turtle.png` | `acadc81bf0ca74b9731eee589496134e19f55460aa984a0ed50e990a944c5466` | 上游公开演示图片 |
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `screenshots/directory.png` | `4a7b4358768f90d30eca5273cd4c21def025518535eb743164a85d178b63e0a3` | 上游公开文档截图 |
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `screenshots/public.png` | `4c3aa1b068e8ada2975250cb752182032513f9d7bbbd3c6b1f852cc7cb8f196a` | 上游公开文档截图 |
| `http-party/http-server@0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b` | `screenshots/start.png` | `f2408298ef05e3eb8d60589234576ceabf92ed6d0fab71b5badc90c804ef3ad0` | 上游公开文档截图 |

## 尚未覆盖的范围

- 本机 Ollama 的 `openguard-action-plan/3` 真机推理为 `NOT_RUN (LOCAL_OLLAMA_STOPPED)`。TASK50 的协议、失败隔离及纠偏门禁均使用确定性替身。
- TASK51 洁净解压复用同锁 CPython 3.12 venv。Linux、WSL2 与 Docker 首次安装，以及 Linux/macOS 跨环境冷启动和一键部署，留待 v2.3 验证。
- 可选模型为 Ollama `0.33.3`、`qwen3:4b-instruct-2507-q4_K_M`，manifest digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。历史 TEST_ONLY 模型证据见 `output/competition/qwen3-workbench-recovery-01/evidence/FINAL_RUNTIME_RECEIPT.json`，SHA-256 `a888ac1284d3ecb244a0abb714541b53a95953471d0fe6570b954229262e2893`。
- `P2_V11_8_HARNESS=NOT_RUN (HISTORICAL BLOCKED)` 为独立的历史验收记录。TASK51 未复跑 Chrome 或重新构建 Vite。
