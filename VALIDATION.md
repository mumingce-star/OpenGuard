# 国赛 P7 候选验证记录

`aic-national-p3-p7-20261122-candidate` 的受测源父提交为 `1f4dc46aab5c494be71c518fe869787a24f679ba`，`application/` 树为 `784c3618a6795d617a0f33257df58d32c2b18f32`，`web/` 树为 `4546d713ea3b38a4d2d8b3627705ff493175a4e9`。P7 只刷新五份顶层交付文件。外部 `TASK42_RECEIPT.md` 和 `TASK42_FILE_HASHES.json` 绑定本地提交、最终 ZIP SHA-256、P7 新实跑结果和原始证据。

## P4 至 P6 的有效证据

- **TASK38C**，提交 `2e97770f1bd1def2aff18399fb0aef74f25c3ec2`，690/690。确认 B58 集成和五项 pnpm 锁定回归。
- **TASK39**，提交 `318799e634f766a1eda0ac2ef9a1e43737b9c1c9`，727/727。四条 Apache-2.0/NOTICE 的 ASGI 路径、版本化 v4、B58 角色和 `A-P4-04` 增量影响集通过。无 NOTICE 为条件 `SUPPORT`，未补 NOTICE 为 `UNKNOWN`，错误 NOTICE 为 `COUNTER_EVIDENCE`，精确匹配 NOTICE 后为 `UNKNOWN`，保留 §4(d) 人工核对提示。
- **TASK40**，提交 `ab2c1256c4a2efb8714cc90b9f39eda0fc5fc224`。既有离线 Vite 构建 5/5 产物、退出码 0，有体积提示。真实 Chrome 20/20，210 条本机应用请求、0 个 4xx/5xx/控制台错误，22 张截图。启动期 7 次后台 CONNECT 被本机代理拒绝，5 次 IPv6 不可达探测发出 0 字节，实际外部 HTTP 为 0。MIT 补材 r1→r2 重算 1/5 个资源及 3/15 条主张，保留 4/5 个资源及 12/15 条主张。历史 r1 原始 DTO 保持，R2 导出绑定实际 Assessment v1、Result r2 和归档。P6 仅新增四个评测文件，P5 后端、前端、web、部署和样例树与 P6/P7 相同。
- **TASK41**，提交 `1f4dc46aab5c494be71c518fe869787a24f679ba`。进程内真实 ASGI 21 场景、48 条去重主张，41 次场景执行及 535 次交换包含冷态、首次评测和暖态重复。严重安全错误 0/48，十类永久安全负例 10/10。程序、冻结清单和指标报告随 `application/benchmarks/` 交付，原始运行证据留在外部。
- **TASK42** 的独立解压检查、合规扫描及同树 744 项复验状态由 P7 外部回执逐项核验。包内清单按公开载荷生成，运行状态和证据原件分开保存。

## 744 项离线门禁基线

| 门禁 | TASK41 证据分母 |
|---|---:|
| CORE_P4_PYTEST | 278/278 |
| TASK39_PYTEST | 21/21 |
| B58_PYTHON_TESTS | 119/119 |
| TASK41_PYTEST | 12/12 |
| CORE_NODE_AND_DTO_TESTS | 288/288 |
| B58_MJS_TESTS | 25/25（20 + pnpm 5） |
| TSC | 1/1 |

同一受保护产品与测试树已记录 **744/744 PASS**，0 FAIL、0 ERROR、0 SKIP。上述实测报告和 JUnit 在工作区 `output/competition/task41-p6-benchmark/`。最终解压与复跑日志落在 `output/competition/task42-p7-final-freeze/`。

## P6 评测结果

| 指标 | 开发集 | 独立 holdout |
|---|---:|---:|
| 项目 / 场景 / 主张 | 6 / 16 / 36 | 2 / 5 / 12 |
| 精确标签匹配 | 29/36 | 9/12 |
| 条件建议精确率 | 7/7（100%） | 0/0（`null`） |
| 支持范围覆盖 | 7/30 | 0/5 |
| 全案例分母覆盖 | 7/36 | 0/12 |
| 发现资源 / Evidence / 摘要验证绑定 / 支持主张 | 124 / 184 / 184 / 7 | 5 / 15 / 15 / 0 |

十条保守漏判是开发 7 条和独立集 3 条。预期为 `SUPPORT`，实际均为 `UNKNOWN`。原始 MIT 格式、Apache 附录占位符等严格模板边界已记入 `application/benchmarks/P6_BENCHMARK_REPORT.md`。holdout 无 `SUPPORT` 输出，因此条件建议精确率无定义。标签为 `SINGLE_ANNOTATOR_FROZEN_PENDING_SECOND_HUMAN_REVIEW`。按 Owner 确认，依赖元数据已有包名引用，已审计范围内无既往命名评测样本，`zero_prior_repo_references=false`。

同输入用途的开发集 15 个配对中，初始全量与补材增量分别重算 119/119 和 15/119，耗时中位数 102.48→13.57 ms，保存的问题对象 238→238，材料/回答动作 0/0→18/1。holdout 4 个配对分别重算 4/4 和 4/4，耗时中位数 97.37→7.79 ms，问题对象 8→8，材料/回答动作 0/0→4/0。初始与增量包含不同操作，记录为配对耗时。问题对象计数没有测量用户工时。

MacBook Pro Mac17,9，Apple M5 Pro，15 逻辑核，24 GB，macOS 27.2.1 arm64，Python 3.12.14。每划分 2 代表场景，冷 1 轮与暖 5 轮均用独立 ASGI 应用实例和临时数据库。各划分冷态 2/2、暖态 10/10，拒绝 0/26 与 0/130，5xx 和超时 0。最近秩分位数如下。冷轮起于新解释器，轮内共享模块导入缓存，系统缓存未清除。

| 接口 p50/p95 ms | 开发冷 n=2 | 开发暖 n=10 | holdout 冷 n=2 | holdout 暖 n=10 |
|---|---:|---:|---:|---:|
| 扫描 | 42.37/59.14 | 42.13/52.56 | 37.22/50.70 | 49.66/59.05 |
| 评估创建 | 28.08/28.68 | 28.33/57.25 | 29.07/43.70 | 27.18/47.42 |
| 材料上传 | 5.42/7.23 | 6.06/7.24 | 4.31/4.32 | 4.02/4.41 |
| GET v4 初始 | 4.80/8.86 | 4.19/5.09 | 2.75/3.77 | 2.44/3.93 |
| GET v4 增量 | 4.58/6.34 | 4.66/6.42 | 2.60/3.45 | 2.83/3.77 |
| 完整评估包导出 | 7.05/8.47 | 7.03/9.35 | 4.15/4.57 | 4.56/4.84 |

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

- `P2_V11_8_HARNESS=NOT_RUN (HISTORICAL BLOCKED)`。本轮没有把历史裁剪或缺证结论改写为通过。
- P7 的解压 `check` 核对 CPython、锁定依赖、Git、固定样例和前端入口。Linux、WSL2、首次安装及跨设备完整启动链未实测。
- 当前固定可选模型身份为 Ollama 0.33.3、`qwen3:4b-instruct-2507-q4_K_M`，manifest digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。P7 不复跑 Qwen。历史独立 TEST_ONLY 恢复证据为 `output/competition/qwen3-workbench-recovery-01/evidence/FINAL_RUNTIME_RECEIPT.json`，SHA-256 `a888ac1284d3ecb244a0abb714541b53a95953471d0fe6570b954229262e2893`。
- G4 最终接纳与可选发布等待 Owner 决策。
