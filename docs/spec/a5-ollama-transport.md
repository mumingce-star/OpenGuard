# A5-1a Qwen3/Ollama 本地 Transport 规格

状态：冻结 v1（Sol，2026-09-04）

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
