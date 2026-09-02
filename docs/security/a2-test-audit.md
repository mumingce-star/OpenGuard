# A2 独立可测性与证据审计

状态：`DESIGN_AUDIT_COMPLETE`

审计日期：2026-09-02

审计角色：Luna（测试验证 / 安全证据）

范围：仅审计 `POS-A2-001..005`、`NEG-A2-001..036` 的设计可测性、边界完整性、结果映射、真实集成要求和证据条件。本文不证明任何 A2 实现已经存在或通过；本轮没有运行 A2 实现测试，也没有修改实现、公共契约或 fixture。

## 1. 判定口径与总览

- `PASS-DESIGN`：设计目标、输入、主要期望和集成层级足够形成可执行测试；仍须在实现后取得真实运行证据。
- `GAP`：目标方向明确，但需要拆分边界、补充稳定错误/状态、运行环境、fixture 或证据字段后才能作为冻结验收项。
- `BLOCK`：必须先有指定的真实基础设施、持久化组件、构建输入或部署 profile；单测、stub 或 mock 不能关闭该项。

总判定：5 个正向项中 1 个 `PASS-DESIGN`、3 个 `GAP`、1 个 `BLOCK`；36 个负面项中 9 个 `PASS-DESIGN`、20 个 `GAP`、7 个 `BLOCK`。这些是设计审计标签，不是测试结果。

当前设计可以作为“条件性测试基线”，但不允许把 S2/A2 标记为最终完成或把 `CLM-07-002` 从 `planned` 提升为 `verified`。TrustedEgress、Linux 安全运行 profile、实际依赖台账和 durable registry 均尚无运行证据；部分测试矩阵还需要拆分。

## 2. 正向验收逐项审计

| 测试 ID | 判定 | 可测性与缺口 | 最低集成层级 |
|---|---|---|---|
| `POS-A2-001` | `BLOCK` | 小型公开 HTTPS Git、固定 commit、inventory 和“不执行”目标清楚；但公网获取必须依赖可记录实际拨号 IP/SNI/字节的 TrustedEgress，不能用普通 Git host 连接或 mock 代替。 | 真实受控 egress + 真实 TLS/Git 服务 + Linux profile |
| `POS-A2-002` | `GAP` | ZIP 普通路径、零/未知 external attributes、哈希和清理目标清楚；仍需锁定 preflight/ZIP 库及其 ZIP64、data descriptor、central/local header 支持矩阵，并把“最后只读消费者结束”作为清理断言。 | 真实 ZIP 字节流/文件系统集成；库版本锁定 |
| `POS-A2-003` | `BLOCK` | 设计已正确设为条件项：只有引入 durable task registry 才能测跨 worker/重启幂等；未引入时只能记录 A3 前置，不能计入 A2 完成证据。 | 真实持久 registry + 两 worker/重启集成；不得以内存 mock 宣称完成 |
| `POS-A2-004` | `PASS-DESIGN` | 空格、非 ASCII、普通标点作为数据，不进入命令或日志注入的期望明确；需覆盖 API、进程 argv、日志和 inventory 四个观察面。 | 单测 + 真实子进程/日志集成 |
| `POS-A2-005` | `GAP` | 稳定排序、size、文件哈希和根摘要可重算；需明确重算时点、输入树只读、inventory 后修改触发失败，以及 Git revision 与 ZIP 无 revision 的差异。 | 真实 dirfd inventory + 重算/变更集成 |

## 3. 负面测试逐 ID 覆盖表

| 测试 ID | 判定 | 审计结论、缺失拆分或精确化要求 | 最低集成层级 |
|---|---|---|---|
| `NEG-A2-001` | `PASS-DESIGN` | 协议/`scp-like` 逐值参数化；须断言网络和 Git 进程均未启动。 | 单测 + 进程启动哨兵 |
| `NEG-A2-002` | `GAP` | userinfo、query/fragment、CRLF、控制字符、二次解码应分别记录；需定义原始值/规范化值的拒绝顺序和无秘密日志断言。 | 单测 + API/日志集成 |
| `NEG-A2-003` | `PASS-DESIGN` | IP literal、端口和 IDNA 可逐值断言 `invalid_source`；应补充 Unicode 混淆及尾点/大小写规范化样例。 | 单测 |
| `NEG-A2-004` | `GAP` | 必须覆盖全部 IPv4 deny 类别，不只 127/私网；需要固定 CIDR 清单并验证“无连接”。云元数据地址须用受控解析结果，不访问真实端点。 | 单测 + 受控 resolver |
| `NEG-A2-005` | `GAP` | IPv6、mapped IPv6、ULA、zone scope 和 mixed public/non-public 必须逐类、逐个 A/AAAA 结果测试；需指定语言/平台分类差异的证据。 | 单测 + 受控 resolver |
| `NEG-A2-006` | `BLOCK` | 直接模式可测零重定向；允许重定向分支必须先有 TrustedEgress，逐跳实际连接、TLS/SNI、降级和凭据不转发不能用 mock 关闭。 | 真实受控 HTTPS/egress |
| `NEG-A2-007` | `BLOCK` | DNS 首次公网、连接前变私网的竞态必须在真实 resolver/egress 连接链路观察实际目的 IP；仅注入两次解析结果不足以证明没有私网拨号。 | 真实受控 DNS + egress |
| `NEG-A2-008` | `BLOCK` | 直接模式任意重定向、TrustedEgress 循环/超限应拆成独立用例；后者依赖真实逐跳代理和清理，不可只测客户端返回值。 | 真实受控 HTTPS/egress + 生命周期 |
| `NEG-A2-009` | `GAP` | `.gitmodules`、gitlink、LFS、filter 和恶意 attributes 要分别测；须区分“不递归/不下载”与 gitlink 按 `git_entry_unsafe` 失败，使用真实 Git object/tree。 | 真实 Git bare/object fixture |
| `NEG-A2-010` | `GAP` | credential helper、hook/template、filter、proxy 要分别放入 system/global/task 环境；同时保存脱敏 argv/env allowlist 和替身无调用证据，不能只检查一个 flag。 | 真实 Git 进程 + 受控替身 |
| `NEG-A2-011` | `PASS-DESIGN` | symlink、绝对目标和循环链接均应在 tree 校验失败，且明确未读取 target；无需访问真实 root 外路径。 | 真实 Git tree + 文件系统 |
| `NEG-A2-012` | `GAP` | case-fold、NFC 和特殊文件应分组；须覆盖大小写敏感/不敏感文件系统、所有特殊 tree mode，并证明拒绝前后无覆盖。 | macOS/Linux 真实文件系统矩阵 |
| `NEG-A2-013` | `BLOCK` | transfer、materialized、file count、single file、disk、timeout 必须一阈值一用例；transfer 需 egress 硬截断，disk/cgroup 需受支持 Linux profile，不能用内存计数替代。 | 真实 egress + Linux resource profile |
| `NEG-A2-014` | `GAP` | 非 ZIP、截断、伪 central directory、多卷、加密应拆开；缺少 ZIP64 EOCD、异常 offset/overlap 和未支持算法的独立用例。 | 真实 ZIP 字节级 preflight |
| `NEG-A2-015` | `GAP` | local/central size 不一致和 CRC 错应分开；还需加入 data descriptor、ZIP64 size/offset、重叠结构，并精确区分 integrity reason。 | 真实 ZIP parser/流式 reader |
| `NEG-A2-016` | `PASS-DESIGN` | `../`、绝对、盘符、UNC/device path 的拒绝目标清楚；需在不同平台只验证策略，不要求访问对应真实设备。 | 路径单测 + 安全写入集成 |
| `NEG-A2-017` | `GAP` | 反斜杠、NUL、控制字符、`.`/空段、深度和长度应分测；深度/长度必须有等于与刚超过阈值，并确定 invalid 与 limit reason。 | 单测 + 真实写盘 |
| `NEG-A2-018` | `PASS-DESIGN` | NFC/case-fold 重名、重复项、文件/目录冲突均要求整包失败、无最后覆盖；应记录父目录类型表和未产生部分 inventory。 | 真实 ZIP + 文件系统 |
| `NEG-A2-019` | `GAP` | Unix/DOS/reparse mode、symlink、hardlink、device/FIFO/socket、setuid 等需按 header 属性逐项；零、缺失、未知属性的普通文件行为需与 POS-002 对称核验。 | 真实 ZIP metadata + 文件系统 |
| `NEG-A2-020` | `GAP` | 上传、总解压、单文件、条目数要拆为四组，并各测默认值“等于”和“刚超过”；目录是否计数、流式实际值与声明值的优先级需在记录中固定。 | 真实 multipart/ZIP 流式集成 |
| `NEG-A2-021` | `GAP` | 单项/整体 ratio 必须分别测 100:1、刚超过、低于；压缩大小为零、声明值与实际值不一致、整数/浮点舍入规则仍未形成可复现断言。 | 真实 ZIP 解压流 |
| `NEG-A2-022` | `PASS-DESIGN` | 嵌套 ZIP/tar 只能作为普通文件，不能递归解压；需确认后续扫描器配置同样关闭递归。 | ZIP + 后续 scanner boundary 集成 |
| `NEG-A2-023` | `PASS-DESIGN` | 父目录替换 symlink 的 TOCTOU 必须以真实 dirfd/`O_NOFOLLOW`/独占创建验证，不能用 SecureRoot mock；root 外不应有创建或修改。 | POSIX 真实文件系统并发集成 |
| `NEG-A2-024` | `GAP` | 需指定在 inventory 前后哪个观察点注入修改，并分别测内容、size、inode/type、摘要变化；期望必须是 `failed`，不能被下游降级为 `partial`。 | 真实只读/并发文件系统 |
| `NEG-A2-025` | `PASS-DESIGN` | `--help`、分号、命令替换、换行、反引号等均应作为数据；须同时观察无 shell 副作用、argv 边界和日志控制字符转义。 | 真实子进程 + 日志集成 |
| `NEG-A2-026` | `GAP` | manifest 的 install/build/test script 与 URL 需分测，明确允许的静态字段读取；须有网络哨兵、执行哨兵和无安装/解释器调用证据。 | 真实进程/deny-egress 集成 |
| `NEG-A2-027` | `BLOCK` | 输入写入、网络、其他任务目录/环境文件访问必须由 Linux container、只读 mount、namespace 和 deny-egress 真实阻断；Python 计数或 macOS 结果不足。 | 真实 Linux sandbox profile |
| `NEG-A2-028` | `BLOCK` | CPU、memory、process、fd、wall-clock、disk 要一项一项测等于/刚超过和终止后状态；cgroup v2/进程组回收/worker 可复用性必须真实观察。 | 真实 Linux cgroup/容器 |
| `NEG-A2-029` | `GAP` | success、validation fail、timeout、cancel、异常须分别测；“立即消失”需改成最后只读消费者结束后清理，且清理失败时应验证 quarantine/worker 不复用例外。 | 真实 supervisor/文件系统生命周期 |
| `NEG-A2-030` | `GAP` | 强退与重启清道夫要真实执行；需固定受控 namespace、TTL/Clock、孤儿命名和权限条件，并证明不触碰其他任务或系统临时目录。 | 真实 worker restart + 文件系统 |
| `NEG-A2-031` | `GAP` | token、私钥、密码、连接串、绝对路径、PII 应分 corpus 并覆盖 API、日志、ScanError、Evidence；需要脱敏前后哈希/计数证据，不保留命中原值。 | 真实输出管线 + 脱敏扫描 |
| `NEG-A2-032` | `GAP` | ANSI/CRLF、HTML、CSV 公式前缀需按 HTML/CSV/终端/Markdown 输出面拆分；A2 触发 A6/F0 门禁的责任、状态和证据位置尚未完全定义。 | 真实序列化/渲染边界 |
| `NEG-A2-033` | `BLOCK` | 只有 A2 实际引入的 Git/ZIP/安全依赖和基础镜像才可验收；必须有锁定版本、来源、digest/checksum/signature 和台账。ScanCode/Syft/规则未引入时只能 `planned`，不能用模拟清单关闭。 | 真实构建/供应链台账 |
| `NEG-A2-034` | `PASS-DESIGN` | 同步安全拒绝为非 2xx envelope；异步安全失败为 `failed`+脱敏 ScanError；明确不得 `partial/completed`。需逐入口验证。 | API contract + supervisor 集成 |
| `NEG-A2-035` | `GAP` | 只允许 inventory 成功后下游可恢复失败为 `partial`，且 `ScanError.recoverable=true`；必须加入输入安全失败对照组，并验证异步 ScanError 不擅自新增 `details.reason`。 | 状态机/错误包络集成 |
| `NEG-A2-036` | `GAP` | 请求不能提高限额，非法管理员配置启动失败；需对每个配置的最小值、最大值、低于下限、刚超过上限和规范化 `config_digest` 参数化。 | 配置启动 + API contract |

## 4. 必须补齐的边界矩阵

“刚超过”不能只写在测试标题中，必须有可重算的输入摘要和实际计数。首批矩阵至少包括：

1. 所有 byte/数量/深度/路径字段分别测试阈值等于值、刚低于、刚超过；包括上传、总解压、单文件、条目/目录数、Git 文件数、materialized bytes、深度和 UTF-8 path bytes。声明值与实际消耗值必须各有观察值。
2. `100:1` ratio 测试应包含低于、等于、刚超过、压缩大小为零且非空、单项与整体；记录分子/分母和舍入方式。Git/ingestion/worker timeout 也要分别在 deadline 前、deadline 触发、deadline 后观察，不用不稳定的睡眠近似。
3. URL 2,048 UTF-8 bytes 和管理员配置每一项的安全下限/硬上限需加入等于与越界用例；`git_redirects_max=0` 的直接模式与受控 egress 的 1-5 分支不能混为一个结果。
4. ZIP 结构必须覆盖 central/local headers、ZIP64 EOCD/offset/size、data descriptor、CRC、重叠/截断、未知 external attributes、Unicode NFC/case-fold 和平台路径差异；每个拒绝项需有稳定 `code` 与 reason。

## 5. 集成层级和不可 mock 的证据

| 层级 | 可测内容 | 不能替代的证据 |
|---|---|---|
| 单元 | URL 规范化、IP deny 分类、路径 NFC/case-fold、ZIP 字段解析、配额算术、配置范围、错误映射 | 不能证明真实拨号、dirfd TOCTOU、cgroup 或跨任务隔离 |
| 契约 | P0 envelope、`ScanRun` 状态机、同步 `details.reason` 与异步固定 `ScanError` message 的差异、`recoverable` 规则 | 不能证明输入树安全或输出管线实际脱敏 |
| 真实文件系统 | dirfd/no-follow、独占创建、tree mode、inventory 重算/变更、清理/quarantine、跨任务目录 | 不能以 SecureRoot/cleanup mock 作为最终通过证据 |
| 受控网络 | 全量 A/AAAA、mixed/rebinding、每跳 redirect、TLS 证书/SNI、实际 destination IP、降级和字节断连 | 不访问真实私网或云元数据；不得以“先解析 host 再让 Git 自己连接”证明 pinning |
| Linux 系统 | non-root、只读输入、network namespace、deny-egress、cgroup v2 CPU/memory/disk、process/fd、进程组终止、worker restart 和跨任务隔离 | macOS 只能是开发级单元/有限集成证据，不能替代 A2 安全完成证据 |
| 构建/供应链 | 实际 Git/ZIP/安全依赖、基础镜像 digest、官方来源、checksum/signature、SBOM/NOTICE/资源台账 | 不得以公开仓库地址、模拟版本或尚未引入的 ScanCode/Syft/规则清单冒充已验证 |

必须真实集成的重点是：DNS 与连接固定、redirect/TLS/SNI/实际目的 IP、Git hook/filter/LFS/credential/proxy/submodule/tree mode、ZIP header/ZIP64/data descriptor/CRC、dirfd TOCTOU、完整生命周期清理、Linux container/cgroup/deny-egress、跨任务隔离及 durable registry。测试服务使用本地或隔离网络中的合成域名/证书和非敏感 fixture，不访问真实内部服务。

## 6. fixture、匿名与证据记录门禁

当前验收文档要求记录 fixture 来源/授权、提交、版本、配置摘要、命令、期望/实际、运行时、复核人和脱敏状态，方向正确但不足以形成可审计的统一记录。每个 fixture/run 至少补齐以下字段（字段补齐不等于修改公共 API）：

```yaml
test_id: <test-id>
fixture_id: synthetic-a2-000
fixture_kind: synthetic | local-controlled-service | repository-object
fixture_digest: sha256:...
source_and_license: internal synthetic / authorized local test asset
authorization_scope: owner-or-team-approved; expiry_or_review_date: YYYY-MM-DD
redistribution: do_not_publish | deidentified_only | public
anonymization_status: pass | fail | not_applicable
secret_scan_status: pass | fail
code_commit: <commit-or-working-tree-id>
runtime_profile: unit | contract | macos-dev | linux-container-v2
git_zip_scanner_versions: <exact versions or not_applicable>
config_digest: sha256:...
command_or_harness: <redacted command/reference>
expected: <stable code/status/reason>
actual: <stable code/status/reason; no raw input>
run_id: <deidentified run id>
input_output_digest: <digest(s), no content>
duration_ms: <number>
evidence_id: <approved evidence id or planned placeholder>
claim_id: <report claim if any>
disclosure_boundary: public | deidentified | restricted | do_not_publish
status: verified | planned | blocked
reviewer_and_time: <role + UTC timestamp>
```

授权必须证明 fixture 可以用于该测试和该披露边界；真实 token、个人信息、学校/教师信息、本机路径、账号、终端历史和第三方受限内容不得进入 fixture、日志、截图或证据。日志只保留摘要、计数、稳定 ID 和版本，不能用“已脱敏”文字代替扫描结果。

证据必须绑定 `test_id`、`run_id`、输入/输出摘要、代码/依赖/配置版本和运行 profile。`planned`/`blocked` 记录不是实现证据；`EVD-PLANNED-A2-TEST-001` 不能因本设计审计完成而升级。报告映射中的 `CLM-07-001`、`CLM-07-002` 及章节九 evidence index 需由 Sol/Root 在后续状态变更时重新核对，本轮不直接修改报告映射。

## 7. Terra/Sol 门禁闭环核对

| 安全项 | Terra 结论 | Sol 回修/当前设计 | Luna 审计闭环 |
|---|---|---|---|
| `SEC-A2-001`,`002`,`005`,`006`,`009`,`011`,`012`,`013`,`014`,`016`,`017`,`019` | `ACCEPT` | 主要行为和错误边界已写入基线 | 设计可测；实现/真实证据待补，不等于完成 |
| `SEC-A2-003` | `ADJUST` | 已要求全量 A/AAAA、显式 deny CIDR、mapped/metadata/mixed | 设计方向闭合；CIDR 清单、平台 resolver 证据和 `NEG-004/005` 仍为 `GAP` |
| `SEC-A2-004` | `BLOCK` | 已把直接模式收紧为零重定向，并要求 TrustedEgress 逐连接记录 host/IP/SNI | 未闭合；`NEG-006..008` 和 `POS-001` 保持 `BLOCK`，直到真实代理集成 |
| `SEC-A2-007` | `ADJUST` | 已明确 transfer quota 由 egress 隧道字节执行，不能由 materialized/disk 计数替代 | 设计已澄清；真实 egress 配额与 `NEG-013` 仍 `BLOCK` |
| `SEC-A2-008` | `ADJUST` | 已要求 central/local 交叉验证、ZIP64、流式 CRC；库选择和畸形 corpus 留给实现 | 规范方向闭合；header/ZIP64/data-descriptor/overlap 测试仍 `GAP` |
| `SEC-A2-010` | `ADJUST` | 已明确零/缺失/未知属性只按普通文件字节流，不恢复链接或权限元数据 | 设计澄清；跨工具属性 corpus 和 `NEG-019` 仍 `GAP` |
| `SEC-A2-015` | `BLOCK` | 已绑定 Linux non-root、只读 mount、cgroup v2、deny-egress 和跨任务 profile | 未闭合；`NEG-027/028` 保持 `BLOCK`，macOS 不能替代 |
| `SEC-A2-018` | `ADJUST` | 已区分 A2 实际依赖与未来 ScanCode/Syft/规则，未引入者保持 `planned` | 设计澄清；实际版本/digest/许可台账和 `NEG-033` 仍 `BLOCK` |
| `SEC-A2-020` | `ADJUST` | 已明确 durable registry 是跨 worker/重启幂等条件；否则转 A3 前置 | 条件闭合而非事实闭合；`POS-003` 仍 `BLOCK`，全配置边界 `NEG-036` 为 `GAP` |

因此，Terra 的 12 ACCEPT、6 ADJUST、2 BLOCK 已被 Sol 对主要语义修订接住，但“文档修订闭环”不等于“测试/部署闭环”。仍有 2 个基础设施 BLOCK 控制项、若干依赖条件和测试拆分缺口；不得因 Sol 已回修而宣称 A2 可验收。

## 8. S2 设计门禁结论与后续关闭条件

结论：**不允许冻结为最终 S2 设计门禁；允许保留为条件性 `FROZEN_DESIGN_BASELINE`，等待以下项目关闭后再冻结验收门禁。**

1. Terra 提供受支持 Linux container/cgroup v2/non-root/只读输入/deny-egress/跨任务隔离的可运行 profile 和版本证据；
2. TrustedEgress 真实证明逐跳 DNS、实际 destination IP、TLS SNI/证书校验、重定向策略和 transfer byte quota；
3. 明确 A2 是否引入 durable task registry；不引入则将跨 worker/重启幂等明确保留为 A3 前置，且不计 `POS-A2-003`；
4. 锁定实际 Git/ZIP/安全依赖和基础镜像，完成来源、digest/checksum/signature、SBOM/NOTICE 和第三方资源台账；未来扫描器保持 `planned`；
5. 将所有 GAP 拆成一阈值一用例，补齐等于/刚超过、ZIP header corpus、生命周期例外、同步/异步错误差异和 fixture 授权/匿名/脱敏/证据字段；
6. 实现后由 Luna 在受支持 profile 运行全部 POS/NEG，绑定脱敏 `run_id` 和 evidence index；Root/Sol 再核对 `verified/planned/blocked`、报告匿名、资源授权和提交材料边界。

在上述条件满足前，`CLM-07-002` 保持 `planned`；任何输入安全拒绝、SSRF、路径/类型/完整性、资源隔离或供应链证据缺失都不能以 `partial`、设计说明或 mock 结果替代。
