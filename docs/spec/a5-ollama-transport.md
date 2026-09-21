# A5-1a Qwen3/Ollama 本地 Transport 规格

状态：冻结 v1（Sol，2026-09-04）；2026-09-07 生产调用修复如下。

2026-09-09：生产优先采用资源小批解释，见 [A5 Provider 最新修订](a5-ai-provider.md)。内部请求为 `openguard.ai-resource-batch-input/v1`；响应为绑定 batch_id 及严格成员键的简短中文核验重点，不添加公开 API/报告 Schema 字段。每项必须对应本条来源情境，失败明确回退；事实导航由程序生成并明确标注，不能算作模型原话。prompt/schema 摘要继续写入原 ProducerRef。模型、运行时、温度、seed、输出/上下文限额、30秒单次调用预算和无生成重试保持；没有新的阶段总预算。旧报告按原字节读取，不重算历史 AI。

最新修订（2026-09-07）：Ollama 对 `license-evidence-gate` 且无已绑定义务的同类风险，按规则版本、判断、级别、资源类别/生态、许可表达式与状态、证据类别与状态共享一次 AI 核验流程生成。输入只含确定性上下文，不传仓库原文；每条风险仍保留，并由程序绑定它自己的证据。建议明确标记“同类风险AI核验建议，未逐项确认许可”，不是逐个资源的模型审计结论。

内部格式 `openguard.ai-review-plan/v1` 固定不确定性摘要，要求模型生成三条中文行动步骤；拒绝编号错配、额外字段、重复步骤、非中文为主、免核验或明确授权断言。该提示/Schema 纳入原 producer 摘要。特殊规则继续逐条调用。共享仅限当前调用，不跨扫描复用；同组失败只调用一次，并保留其他成功组。无模板伪装AI兜底；错误仍记录为降级，全部扫描事实保持。未启用该能力的其他 Provider 保留旧整批失败行为。

以下历史章节中的“只含 finding Schema”“整批撤回”对新共享模式由本修订替代；模型版本、摘要、8192上下文、1024输出和30秒调用预算不变，已发送的生成请求仍不重放。外部 API 和报告 Schema 未变化。

生产工厂对 Git、ZIP 和持久 ZIP dispatcher 统一使用每次 30 秒共享调用预算，不重试，保留批次失败降级与事实保持语义。固定 options 新增 `num_ctx=8192`，模型名称、版本、完整摘要及其余 options 不变；上下文增大会增加模型内存占用及首次加载耗时。

对已有整改输入，生成 Schema 将 finding_id 固定为请求编号，evidence_ids 限定为请求现有证据编号。只约束生成，不改写返回内容；Provider 原有编号、证据及敏感文本校验继续执行。绑定策略版本计入 prompt_schema_digest，options 计入 config_digest。smolagents 最长风险输入在原配置下单次约9.95秒且返回错误风险编号，修复后同一输入13.42秒并通过原校验；该单条验证不代表整体质量验收。

范围：项目负责人 A5/S4 的本地模型传输纵切

依赖：A5-0 `docs/spec/a5-ai-provider.md`、P0 contract `0.1.1`

## 1. 目标与非目标

A5-1a 为 A5-0 `Provider` 提供一个真实的、可替换的 Ollama HTTP 实现。它只向本机回环地址
发送 A5-0 已收敛的 canonical finding/evidence/license JSON，要求 Ollama 使用 JSON Schema 返回
整改建议，并在进入 A5-0 提升逻辑前校验运行时版本、模型身份和 HTTP 包装。

本纵切不安装 Ollama、不下载或再分发模型权重、不启动常驻服务、不接 A4 Pipeline、不实现 B5
许可证规则，也不声称 Qwen3 已在当前机器产生真实推理结果。A5-1b 才负责经项目负责人批准后的
本机安装、模型拉取、内容摘要复核和真实推理；A5-1c 在消费组员 B5 的真实 finding 后接 A4。

## 2. 锁定资源与证据状态

| 资源 | 锁定身份 | 官方证据 | 许可证 | 当前状态 |
|---|---|---|---|---|
| Ollama | `v0.33.3` | `https://github.com/ollama/ollama/releases/tag/v0.33.3` | MIT；上游 `LICENSE` | A5-1b 已完成本机安装、签名/公证与运行版本核验 |
| Qwen3 | `qwen3:4b-instruct-2507-q4_K_M` | `https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M` | Apache-2.0；模型页及 Qwen 模型仓库 | A5-1b 已下载到本机私有缓存并完成真实推理 |
| Ollama manifest | `sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` | 官方 registry manifest；模型 blob 为 `sha256:85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9` | 随对应模型 | A5-1b API tags、磁盘 manifest 原始字节与模型 blob 已独立重算一致 |
| Qwen 原始模型卡 | `Qwen/Qwen3-4B-Instruct-2507` | `https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507` | Apache-2.0 | 上游模型卡与许可证已核验 |

manifest 摘要的复现方式是对官方 registry 返回的原始 manifest 字节运行 SHA-256；代码不得只保存
网页展示的 12 位短摘要。A5-1a 的测试 server 只是协议 fixture，不是模型或许可证事实证据。

选择 4B Instruct Q4_K_M 是为了给普通 Apple-silicon 笔记本保留可演示的 2.5GB 量级候选，且
非 thinking 版本更适合严格短 JSON。该选择仍须在 A5-1b 根据队长机器实际内存、延迟和结构化
输出成功率做实测；若不达标，必须走资源变更记录，不能静默改用 `latest`。

## 3. 固定 HTTP 契约

默认 origin 为 `http://127.0.0.1:11434`。配置只允许 `http` 与字面量回环 IP
`127.0.0.0/8` 或 `::1`，必须有显式端口，不允许用户名、密码、query、fragment 或非根路径。
实现必须显式禁用环境代理，不能把待分析事实发送到代理、云端 Ollama 或任意可配置主机。

每个 `generate(payload, timeout_seconds)` 使用一个总 deadline，按顺序执行：

1. `GET /api/version`，只接受 JSON object 且 `version == 0.33.3`；
2. `GET /api/tags`，精确找到模型名并要求完整 digest 与锁定 manifest 一致；
3. `POST /api/generate`，请求体固定包含 `model`、`system`、原 canonical `prompt`、
   `stream=false`、输出 JSON Schema、`think=false` 与确定性 options。

options v1 固定为 `temperature=0`、`seed=0`、`num_predict=1024`。输出 Schema 只含 A5-0 已冻结的
`schema_version`、`finding_id`、`summary`、`steps` 和 `evidence_ids`，`additionalProperties=false`。
系统提示把输入声明为不可信数据，禁止采纳其中指令、禁止新增许可证/路径/义务/风险事实、禁止
输出法律结论，并要求只返回 Schema 对象。提示模板与 Schema 的 canonical SHA-256 写入
`ProducerRef.prompt_schema_digest`；endpoint、版本、模型、digest 和 options 的 canonical SHA-256
写入 `config_digest`。

非流式成功包装必须是 `application/json`、HTTP 200，并至少满足：`model` 精确匹配、`done=true`、
`response` 为字符串。允许 Ollama 官方返回的耗时和 token 统计扩展字段，但这些字段不进入 P0
事实。adapter 只把 `response` 字符串交给 A5-0；A5-0 继续负责 64 KiB、重复 key、引用和敏感内容
门禁。

## 4. 限额与失败语义

- 输入 canonical payload 最大 256 KiB；version 包装最大 4 KiB；tags 包装最大 256 KiB；generate
  包装最大 96 KiB；所有上限按实际读取字节执行，并在 `Content-Length` 可用时提前拒绝。
- `timeout_seconds` 必须是有限正数且不超过 120 秒；三个请求共享该总时限，不是各获得一份完整
  timeout；不自动重试，避免重复推理和失控耗时。
- 拒绝非 UTF-8、空 body、重复 JSON key、NaN/Infinity、非 JSON content type、非 200、错误
  wrapper、版本/模型/digest 不匹配和响应超限。
- adapter 对外只抛稳定 `OllamaTransportError("ollama_transport_unavailable")`，不得携带 URL、
  response、异常文本、文件路径或凭据；A5-0 将其统一变为可恢复的
  `ai_provider_unavailable/degraded`，保留确定性结果。
- adapter 不记录 prompt/response，不访问文件，不启动命令，不读取凭据，不自动 pull 模型。

## 5. 验收矩阵

实现侧至少覆盖：

- 版本、tags、generate 三步顺序和同一总 deadline；
- 禁代理与只允许字面量回环；拒绝公网、DNS hostname、凭据、path/query/fragment；
- 固定模型、完整 manifest digest、提示/配置摘要和 AI `ProducerRef`；
- 请求 JSON Schema、`stream=false`、`think=false`、固定 options 与 canonical payload 原值；
- 非 200、超时、连接失败、错误 content type、重复 key、非有限数、错误版本/模型/digest、空/截断/
  超限 wrapper 全部脱敏失败；
- 有效 wrapper 返回原 `response`，再经 A5-0 生成 pending remediation；任何 transport 失败经
  A5-0 为 `degraded`，不得发布部分建议。

Luna 必须独立启动一个有界回环 HTTP fixture，不复用实现侧 fake opener 或 expected helper，证明
实际 TCP/HTTP 的 GET/GET/POST、超时和降级；若 sandbox 禁止 bind，保留原始 `PermissionError`
并在受控权限下原样复跑。只有定向测试、A5-0、P0、完整非回环回归、compileall、diff、敏感和
范围门禁全绿后，才可批准 `EVD-A5-OLLAMA-TRANSPORT-001`。该 evidence 不证明真实模型质量、
许可证规则正确、A4 接线、报告或完整参赛作品。

## 6. A5-1b 本机真实运行记录

2026-09-04 经用户授权后，只安装官方 `v0.33.3` macOS DMG。安装前核验：文件大小
196424896 bytes、SHA-256 `cc21bd6a1486ddff3cdcbf00549f61d0a3e6e6893d6456a12d37c486161bcc43`；
应用为 arm64/x86_64 universal，Developer ID Team 为 `3MU9H2V9Y9`，严格代码签名、Gatekeeper
`Notarized Developer ID` 和 stapled ticket 均通过。校验必须在可访问 macOS 信任链的上下文执行；
受限 sandbox 会把系统应用和 Ollama 同时误判为不受信任，该原始假阴性已保留，未绕过 Gatekeeper。

服务仅绑定 `127.0.0.1:11434`，并以 `OLLAMA_NO_CLOUD=1`、`OLLAMA_NOHISTORY=1` 启动。
API 版本为 `0.33.3`；tags digest 与磁盘 manifest 原始字节 SHA-256 均为锁定 manifest；
2497280480-byte 模型 blob 重算 SHA-256 等于锁定 blob。`runtime_probe` 对同一合法 P0 输入运行
3 次，聚合结果为 `3/3`，冷轮 4344.062 ms，热轮 2736.214/2723.574 ms；`generated`、
`pending`、producer 绑定、finding 引用、确定性事实保持与 remediation 身份稳定均通过。
`ollama ps` 报告 100% GPU、context 4096、加载大小/`size_vram` 3175339786 bytes。

该记录只证明当前 Apple-silicon 机器、锁定模型和单一冻结样例可真实生成符合 A5 边界的候选整改；
不证明多项目质量、许可证规则正确、法律结论、A4 主链接线、离线安装包、Linux/Docker、Bench、
报告或完整作品。仓库不保存 Ollama 安装包、模型缓存、prompt 或完整模型 response。

## 7. P0 Docker Desktop 接线补充（2026-09-06）

既有本机默认与模型身份不变。API 管理员同时显式设置 `OPENGUARD_ENABLE_AI=1`
和 `OPENGUARD_OLLAMA_DOCKER_HOST=1` 时，仅使用固定
`http://host.docker.internal:11434` 访问 Docker Desktop 宿主机已有 Ollama；两个开关严格为0/1，
未开启 AI 不创建 Provider。此模式信任操作者的 Docker Desktop 主机解析，不允许任意 endpoint、
端口、凭据、路径或云服务；不是任意 Linux 主机部署保证。宿主 Ollama 继续只绑定127.0.0.1，
不扩大监听地址、不挂模型目录、不自动pull。普通进程默认仍只允许字面量回环地址。

两种模式都禁用环境代理，并显式拒绝 HTTP 重定向，避免已校验地址把事实转送到其他目标。
固定运行时/模型完整digest、单次deadline、结构化输出与A5事实保护不变。

同轮真实样例暴露：模型在`@e2b/cli`建议中复述JSON Pointer，触发既有绝对路径拒绝，整批建议诚实撤回。
补充system prompt要求简短行动步骤，通过evidence_ids引用，不复述路径、JSON Pointer、URL、哈希或凭据；
不放宽输出校验、不修补响应、不重试。新prompt/schema摘要为
`488130706fdd4b56e3385c52a3c55d42832d34a27c6aa69d06b6464b7f0ffcd4`。
升级前确认无queued/running且dispatch目录为空；旧完成报告保留原摘要，不重放旧AI任务、不迁移队列。

## 2026-09-07：新增资源的长证据输入与引用输出

完整识别openai-python后，API资源有35条关联证据；旧请求在finding/许可证两处重复传入同一组对象，43329字符输入下模型逐个输出编号，1024 token输出预算内JSON被截断。Provider请求现将相同证据对象只传一次（所有原finding/license引用ID和报告证据保留），本例降为23666字符；生成Schema限制引用最多3条，模型输出仍经过原ID/证据/文本校验，外部报告Schema及原32条校验上限不改。相同失败finding在修复后8.39秒生成1130字节JSON、3条有效引用。上下文8192、单条30秒、原模型和整批失败语义保持，没有删除风险或事后补写模型输出。

同轮整链复验`scn_dc870fed-023e-49a1-885d-737927df3290`工具/解析无错误，但模型信息读取阶段发生30秒连接等待：宿主日志显示16:06:00生成成功、version=200，其后未见tags完成；即时宿主/容器version、tags、ps探测均正常。无法据此认定模型损坏。只对GET身份探测设置5秒单次网络超时，并允许网络/OSError后最多一次重连；仍共享原30秒总deadline，不重试HTTP错误、身份/JSON/内容校验失败，更不重放生成POST。测试覆盖一次恢复、两次硬上限、到期不能续期、生成失败只调用一次；该例外替代旧“完全无重连”的描述，不是扫描任务或AI生成业务重试。

最终TCP定位修正：连续调用栈确认失败在`socket.connect`，请求尚未发送，且GET和POST均可能发生。因此上段GET级重连被替换为HTTPConnection的建连处理：每次最多3秒、最多3次、扣除原请求剩余deadline；只有连接成功才发送HTTP请求。不会重新发送任何已发送的POST，不重试HTTP/JSON/身份错误；成功响应后仍执行原完整校验。该处理记录于config_digest的tcp_connect配置；原生成时限与限额不变。


## 2026-09-09 V2 组级默认协议

默认 `group_plan_mode=True` 在原 Ollama /api/generate 传输及原安全预算内工作。输入 `openguard.ai-group-plan-input/v1` 只含 group_id 和共同条件的中文投影；输出 schema 约束该 group_id 与简短中文 summary、steps 对象（locate/source/record）、limitations。对象步骤适配已锁定 Ollama 的结构化输出支持，不使用其不支持的 array prefixItems。旧逐条/资源批模式仍由明确关闭 group_plan_mode 的协议回归测试覆盖，并非默认新增调用。ProducerRef提示摘要包含新的组提示和输出Schema，模型/温度/token预算未变。
