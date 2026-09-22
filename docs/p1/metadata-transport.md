# A07-1：受限 Metadata transport 调用交接

这是 A07 的内部实现说明，不是第二份权威 Contract，不是 ResourceProfile DTO。
权威语义仍是 `docs/spec/p1-workspace-contract.md`（尤其 DECISION-05）。
给 cz 的调用边界待双方接线 Review；此文件不表示 B01 已被交付或接受。

## 支持范围与官方依据

仅匿名 HTTPS `huggingface.co:443` 的 model/dataset 信息 GET，无搜索、批量、
README/权重/数据/许可证全文下载，无 token、cookie、私库或 gated 认证流程。
不做 ModelScope、缓存、sidecar、Profile API、refresh/job、Notice、Graph/Report
改动或前端；未接入生产工厂或 `dev_integration`。

2026-09-17 查阅：

- [官方 Hub API 文档](https://huggingface.co/docs/hub/api) 已将端点说明迁至 OpenAPI；
  官方 `/.well-known/openapi.md` 本次浏览工具未成功打开，不声称已读取其内容。
- [官方 SDK hf_api.py](https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/hf_api.py)
  的 `model_info`/`dataset_info` 构造 `/api/models/{repo_id}`、
  `/api/datasets/{repo_id}`，显式 revision 时追加 `/revision/{revision}`；
  `ModelInfo`/`DatasetInfo` 用 `id`、`sha` 表示身份及该 revision 的 SHA。
  仅据此确认协议；未安装、复制或执行 SDK，没有调用真实资源端点。

本批不传查询参数或任意 header。repo ID 支持一段或 `namespace/name` 两段，
总长≤193，每段1–96个ASCII字符，首字符为字母/数字/下划线，其余还可含点/连字符。
禁止段末点/连字符/`.git`、`..`、`--`。大小写保留，不猜测重命名/别名。
这是官方协议的保守子集，不承诺支持所有合法 Hub 名称。

revision 必须显式选择：

| revision_mode | requested_revision | 含义 |
|---|---|---|
| fixed | 40位小写十六进制 SHA | 不补齐短 SHA，不重写大小写 |
| symbolic | 1–128个ASCII字母/数字/下划线/点/连字符；首位无点/连字符，禁`..`、尾点/`.lock` | 如显式 `main` 或 `v1.0`，不假装不可变 |
| default_observation | `None` | 调用方明确选择默认分支当前新观察，不补出扫描当时版本 |

斜杠复杂 ref（含 PR refs）、百分号/重复编码、反斜杠、空白、控制字符、
userinfo、query/fragment 全部不支持。纯 `build_target()` 拒绝非法字段时无 DNS。
不能输入任意 source_url。调用方必须从已有可靠事实取 provider/kind/identity，
transport 不从 runtime provider 推断，不搜索或 fuzzy 补齐，也不验证旧 Scan 引用的存在性。

## 调用与 cz 交接

```python
from app.ingestion.metadata_egress import MetadataTransport, MetadataRequest

request = MetadataRequest(
    provider="huggingface", resource_kind="model", repository_id="synthetic/Model",
    revision_mode="symbolic", requested_revision="main",
)
transport = MetadataTransport()  # 默认关闭；fetch立即feature_disabled，无DNS/DoH/socket
# 管理侧经独立批准才能构造 MetadataTransport(enabled=True)。本轮没有真实调用。
# temporary = transport.fetch(request)
# parser(provider=temporary.source.provider,
#        bounded_bytes=temporary.bounded_bytes(), source=temporary.source)
```

合成 consumer：`tests/fixtures/p1/metadata-transport/synthetic_consumer.py`。
它仅检查字节长度/摘要，不联网、不写DB、不解释许可证，不接收或修改 Scan/Assessment。
不能将这些 synthetic 用例计入 B01 真实5模型+5数据集验收。

`TemporaryMetadata` 暂持内存 bytes，repr不显示内容，不是dataclass，不支持默认JSON
或pickle dump。parser只可在当前调用消费，禁止将完整 raw 存数据库、临时文件、日志、
HTTP响应或通用 dump；直接拿到 bytes 仍需调用方遵守边界，这不是防恶意同进程代码的沙箱。
释放引用不等于物理安全擦除。

`source` 是冻结内部 descriptor：provider/kind/repository_id、请求revision及模式、
来自 `/sha` 的 resolved_revision、revision_locator、version_status、受限source_url、
真实UTC fetched_at、规范化content_type、实际body_size/body_sha256、transport/descriptor
version、full_response_replay_available=false。不生成parser_version、旧Evidence ID或授权结论。

`id` 必须与请求精确相等；有 `sha` 时须40位小写SHA，fixed请求还须相等。
缺少/null `sha` 时仅标 `bounded_content_revision_unconfirmed`，不复制requested值。
有可靠 `/sha` 时标 `revision_observed`：仅确认本次响应报告的仓库revision，
不是声明整个远端 API JSON 永久不可变。响应 body SHA256不是Git SHA，也不是ETag，
更不是后续规范化观察内容Hash。B01 已提供
`app.scanners.huggingface_metadata.HuggingFaceMetadataParser`、稳定字段 locator 与缺口；
其输入/输出边界见 `docs/p1/b01-huggingface-metadata-parser.md`。
存储仍只允许规范化观察、最多1000字符excerpt与来源，不保存完整raw。

## 地址、TLS、DoH 与时间

`metadata_wire.py` 是内部局部适配，不是向请求方开放的URL获取器。
内容目标只有huggingface.co；DoH基础设施另为cloudflare-dns.com，固定bootstrap
1.1.1.1/1.0.0.1。两次A/AAAA请求复用既有DNS codec，额外绑定question原字节，
HTTP读取改用本模块共享 deadline，不改原 `doh_resolver.py` 的P0行为。

所有DNS结果先经既有 `resolve_and_require_public` 检查；任一非法/非公网/映射IPv6
拒绝，结果为空/过多拒绝，不只挑第一个安全地址。socket直接dial已验证数值地址，
无第二次getaddrinfo；拨号前后及TLS后检查peer。失败候选只能来自这一次集合。
仅TCP拨号失败可尝试下一候选；TLS/HTTP/429/5xx不重试，无系统resolver/代理降级。

Host/SNI/证书hostname均为官方主机而非连接IP。SSLContext使用PROTOCOL_TLS_CLIENT、
CERT_REQUIRED、check_hostname、系统可信根、最低TLS1.2与HTTP/1.1 ALPN。
不调用会自动读取SSLKEYLOGFILE的create_default_context；不读HF token/netrc/cookie，
不读取代理变量，不发Authorization/Proxy-Authorization/Origin。调用方无header/TLS开关。

| 实现预算 | 默认/最大支持值 |
|---|---|
| 请求总网络预算 | 20秒（配置最多60秒） |
| 单次阻塞操作 | min(5秒, 剩余总预算)，配置最多60秒 |
| 候选尝试 | 每次exchange最多2（最多配置4），集合已完整校验 |
| DNS结果 | A+AAAA共16（计重复项，校验后去重） |
| body | 1 MiB；DoH单响应64 KiB |
| header | 总32 KiB、单行8 KiB、64字段 |
| wire | 每exchange额外总量≤2×body上限+header上限，包含chunk framing |
| JSON | UTF-8严格、根object、深度32、节点50000、整数100字符/浮点token64字符 |

Limits只可在既定最大值内调整。所有DoH请求、bootstrap尝试、内容候选、connect、
TLS握手、send/recv共用一个单调deadline；每个网络阻塞操作设置剩余timeout，
小块慢发不刷新总预算。无后台future/线程冒充取消。同步可信证书加载和有界JSON
CPU解析不是可抢占实时系统；大小/深度/token限制约束工作量，处理间检查deadline，
不宣称操作系统调度、文件系统或CPU硬实时保证。

流式累计实际字节，Content-Length提前拒绝超限；支持有界chunked和close-delimited，
提前EOF/矛盾长度拒绝。使用已锁定API运行闭包中的h11 0.16.0解析HTTP（不是dev依赖
httpx2，也不是新增/升级依赖）；另加原始header总量/行/字段/重复检查，拒绝折行、
冲突TE/CL、非JSON、压缩编码、interim/upgrade和非空trailers。长度内额外已缓冲字节
也拒绝；成功只取单个HTTP消息，不继续复用连接。全部redirect拒绝（max_redirects=0），
没有逐跳跳转能力。JSON重复键、NaN/Infinity、非有限浮点、过大数字、孤立surrogate拒绝。
失败不返回部分JSON，关闭关联资源；上游body/Location/底层异常不进入稳定错误。

## 错误与未来接线

内部 `MetadataError.code`：feature_disabled、unsupported_input、address_policy_rejected、
dns_failed、connection_failed、tls_failed、timeout、redirect_refused、response_too_large、
response_invalid、json_invalid、identity_mismatch、revision_mismatch、upstream_404、
upstream_access_denied、upstream_rate_limited、upstream_unavailable。
HTTP拒绝保留安全整数 `upstream_status`（包括具体redirect/5xx）；异常文字只有固定code，
不附上游header/body。403/404只记录匿名请求的观察，不断言资源绝对不存在。
无假空对象、缓存凭据补救或替代资源重试。
未来API/job可将关闭映射既有503 feature_disabled，传输失败映射503 upstream_unavailable，
无效观察映射422 metadata_invalid；具体job/item设计另行批准。本轮无公开API/新错误码。
模块不导入Scan registry/Assessment/Report服务，失败不改扫描状态、不触发重扫或模型调用。

## 验收口径与未关闭门禁

本轮使用合成DNS、假socket/TLS上下文注入，以及真实HTTP parser/读取路径测试；
TLS配置/证书故障注入验证不等于真实握手，更不等于真实HF TLS已通过。
默认DoH完整codec与HTTP路径也以合成字节执行，不仅mock最终业务返回。
真实外部Git集成测试 `test_a2_public_git_trusted_egress_integration.py` 未授权运行；
现有A2 unit中的临时loopback代理仅本地合成socketpair，无外网。

仍待：负责人与cz接口Review、B01业务parser与真实可再分发样例、单独授权的真实联网/TLS
验收、sidecar/refresh/job/Profile API、前端、Windows/原生Linux和生产启用。
本轮只做A07-1本地实现和离线验证；不宣布A07、Profile或P1全部完成。
