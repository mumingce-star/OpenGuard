# A3/A4-3a ZIP 持久派发与中断收敛

规格门禁：`A3/A4-3a-S`；状态：`FROZEN-FOR-IMPLEMENTATION`（2026-09-05 三角色复审通过）。
实现包：`A3/A4-3a-I1` 已通过实现、独立与Root全量验收，并发布绑定`272f5cf`；`I2` 已通过实现、独立与Root全量验收；发布绑定见第13节。
原规格批准与实现证据分开，I1证据和边界见第12节。
规格冻结时的代码基线：`1ba14aff6894aabdd25f4491688df5d7b852e95a`。
责任：项目负责人 A 线；Root 统筹，Sol 架构审查，Terra 实现，Luna 独立验证。

## 1. 问题与本包交付边界

当前 ZIP 请求已经持久化 ScanRun，但派发只存在于 FastAPI BackgroundTasks；
进程退出后 queued/running 可能永久悬挂。既有实现必须复用，不能重新生成注册表、
Pipeline、AI Provider、报告器或第二套公共模型。

本包只增加单机 ZIP 持久派发：请求输入及执行配置可恢复，queued 在新进程中消费；
已进入 running 的任务在进程中断后保留最后提交事实，诚实结束为 partial/failed，
不自动重放任何 handler。它解决排队丢失和状态悬挂，不保证扫描一定成功完成。

明确不包含：Git 持久恢复、accept 时锁定 Git commit、lease/heartbeat 接管、
多 worker/多机/NFS、业务阶段 retry、checkpoint、outbox、外部副作用 exactly-once、
未知 orphan 批量清理、Linux 隔离、B2–B7、前端和 Docker。
这些仍属于后续工作；本包完成也不能将持久 worker 父包整体标为已完成。

## 2. 既有实现与冻结边界

| 现有位置 | 必须复用的行为 | 本包不得采取的捷径 |
|---|---|---|
| `backend/app/persistence/scan_registry.py` | 完整 P0 快照、幂等、revision CAS、单向状态 | 不增加表/列/index，不改 v1 allowlist，不改 running 回 queued |
| `backend/app/pipeline/worker.py` | queued 认领、七阶段、失败聚合、首次 terminal CAS | 不重建 worker，不在恢复时再次调用 run() 处理 running |
| `backend/app/api/service.py` | ZIP fingerprint 与 queued 构造 | 不改变幂等指纹；只允许内部拆分 candidate 构造与提交 |
| `backend/app/api/zip_scan.py` | 流式限额、服务端 basename、实际字节 digest | 不在持久任务尚未 terminal 时无条件删除输入 |
| `backend/app/pipeline/local_zip.py` | 一次性 plan、实际流摘要、pristine 校验 | 不序列化闭包；新 queued 才重建 plan，basename 必须保持 source 匹配 |
| `backend/app/pipeline/dependency_plan.py` | 会话内 parser/map、B5/A5 接线 | 不把 parser 移到已过期会话外，不重写 B 线 |
| `backend/app/reporting/` | 私有 artifact、四格式 publisher、registry 可见性门禁 | 不凭磁盘 orphan 推断已发布，不在恢复时补写 links |

P0 v0.1.1、Schema/sample、六 API 路径、请求字段、202 响应结构及 ErrorEnvelope 保持不变。
正常新任务继续调用原 worker 与 A6 publisher；普通真实 ZIP 仍可诚实为 partial/rules/70。
新增的是服务内部派发协议与脱敏 ScanError，不产生新的公共状态枚举。

## 3. 单机运行方式与锁

- 首版通过 `OPENGUARD_ENABLE_DURABLE_ZIP=1` 显式启用，默认 `0`，仅接受精确 0/1。
  未启用及未注入 dispatcher 的既有测试应用保留原 BackgroundTasks 行为。
- durable 模式在接收请求、恢复任务或启动 worker 前取得数据目录内固定私有锁文件的
  非阻塞独占 `flock`。失败则该实例启动失败，不边服务边缺失 worker。
- 锁文件不删除、不替换；验证 owner、普通文件、0600、no-follow 与 inode 身份。
  FD 不得继承到子进程，不能通过 fork 扩大持锁关系。只支持同一本地私有 POSIX 数据目录。
- FastAPI 进程内只有一个 ZIP dispatcher 执行线程；启动 reconcile 完成后才开始接收请求。
  enqueue 的提交片段、reconcile 与 descriptor 清理共用进程内互斥；执行 handler 不持该互斥。
- 锁从生命周期开始持有至停止接收/派发、活动 worker 结束、registry 关闭之后。
  不能因 shutdown 等待超时而释放锁并留下活动线程；需要强制退出时由进程退出释放锁。
- 不用时间、PID 存在性、lease 过期或心跳丢失授权接管。flock 约束合作实例，不能撤销
  已发送的网络调用或控制忽略协议的外部写者；所有事实写入仍须通过 A3 CAS。
- Git runtime 维持既有行为。恢复器不处理 Git 或无 descriptor 的 legacy ZIP 记录。
  durable 模式与 legacy 模式不得同时对同一数据目录提供服务；运行说明必须明确单实例约束。

## 4. 私有输入与 descriptor

沿用 `data/uploads` 中的服务端随机 ZIP basename，不新增 content-addressed 输入副本系统。
在完整上传、文件 fsync 及父目录 fsync 成功后才允许提交 descriptor；原用户文件不属于清理范围。
输入一直保留至 registry 已确认 terminal。每次派发前重新验证文件身份、owner、0600、
普通文件、非链接、大小与 SHA-256；实际扫描仍由 A4-1 再核验实际输入流。

新增运行目录 `data/dispatch`（0700），每个任务最多一个正式 descriptor（0600）：
`<scan_id>.prepared.json` 或 `<scan_id>.ready.json`。文件名状态是内部提交标记，
prepared→ready 使用同目录原子 rename 并 fsync 目录；两者同时存在视为冲突，不猜测赢家。
临时写文件也须私有；不能把仅写入 page cache 描述成持久提交。

descriptor 是可重建派发所需的最小元数据，不是第二份 ScanRun。固定键为：

| 键 | 约束 |
|---|---|
| `schema` / `version` | `openguard.zip-dispatch` / 整数 1 |
| `scan_id` | 与文件名及 registry ID 完全一致 |
| `source_type` | 仅 `zip` |
| `upload_name` | 服务端生成的无路径 basename，等于 project.source |
| `input_sha256` | 64位小写十六进制，等于 provenance.input_digest.value |
| `run_identity_sha256` | 下述不可变身份投影的 canonical JSON SHA-256 |
| `execution_profile` | 精确结构：plan_version、ai_requested、ai_identity、ai_timeout_seconds |

身份投影取 ScanRun 的 contract_version/id/idempotency_key/created_at，
project 的 id/name/source_type/source/created_at，以及 provenance.input_digest；
采用 UTF-8、sort_keys、无多余分隔空格、禁止 NaN 的 canonical JSON。
不含可变 status/stage/progress、project.revision/root_digest、资源或报告。

JSON 限 8 KiB；拒绝未知/重复键、非法 UTF-8、非有限数、bool 冒充整数、未知版本和
不匹配身份。descriptor 不保存原始路径、密钥、prompt、response 或完整模型内容。
目录和权限只防止非授权用户访问，不声称能抵抗同一用户恶意篡改全部本地状态。

输入留存不得无界增长：首版保留既有单文件 64 MiB 上限，另设服务端最多 8 个
未清理 ZIP 输入、压缩字节合计不超过 512 MiB。在读取multipart首个字节前，原子预留
1个slot和完整64 MiB预算，不能在表单解析器已缓存上传之后才预留；文件fsync与descriptor
提交成功后才下调为实际压缩字节。失败释放内存预留，但已留存文件立即转为实际占用，不能漏计。
重启后uploads中全部未清理私有普通文件按实际大小计入；可疑/不可测对象阻止新接收，
不能按零计数或擅自删除。清理失败/无主残留占用配额。默认值为本包设计限额，不是性能实测。
容量不足不创建新任务，沿用 `500/internal_error` 信封，reason=`dispatch_capacity_exceeded`。
禁止通过盲目删除未知 uploads 文件腾出容量；完整 orphan GC 另立任务。

## 5. 执行配置不能在重启时静默变化

`plan_version` 首版为 `zip-dependency-v1`，代表受支持的执行语义版本，不是任意 Git HEAD。
`ai_requested` 是接收时管理员 AI 开关；ai_identity 在 false 时为 null，true 时包含
现有 A5 锁定的 provider/model_id/runtime_version/manifest_digest/prompt_schema_digest。
不新增另一份模型版本常量，以现有 A5 身份定义为来源；timeout 为正有限秒数，沿用运行配置。

- 原任务 AI 关闭：即使重启后管理员开启 AI，该任务仍关闭。
- 原任务 AI 开启、当前管理员关闭：不擅自开启，不静默改成无 AI 执行，按
  `dispatch_profile_disabled` 在 handler 前诚实失败。
- profile 版本或 A5 锁定身份不再兼容：`dispatch_profile_mismatch`，不调用 handler。
- 版本匹配但实际 Ollama 不可用仍由既有 A5 失败降级处理，不在派发准备时调用模型探测。
- 本包不消费外部 B 线候选。将来改变计划/规则语义时须显式评估 profile 兼容，不把新语义
  默认为旧队列任务的执行方式。配置快照不改变 P0 初始 ai_enabled=false 的既有语义。

## 6. 接受请求、幂等与崩溃窗口

内部允许拆分 `create_zip_scan()` 的 candidate 构造与 registry 提交，以提前得到 scan_id。
保留旧方法签名/行为供既有调用者使用；不得另造公共请求模型。

新任务顺序：

1. 沿用字段/上传安全门禁，生成并持久化完整私有 ZIP。
2. 构造合法 queued candidate，持久化 prepared descriptor。
3. 调用既有 registry.create，以原 ZIP fingerprint 执行幂等。
4. 若确为新行，核对绑定后将 prepared 原子提升为 ready；两份持久事实确认后才能返回202。
5. 唤醒 dispatcher 仅是优化；丢失唤醒由周期扫描 ready 弥补，不依赖内存队列保证正确性。

同 key/同字节返回原 scan_id、原任务及原 profile，不因新管理员配置变化改写指纹或变成409。
只清理本次未成为原任务的新 candidate ZIP/descriptor，不删除旧输入，不新增第二个ready。
同 key/不同字节保持原409语义。命中 legacy 或已终态任务仍遵守既有幂等返回，不自动收编；
legacy queued返回原任务不构成持久派发承诺，不为它生成descriptor或自动消费。
新任务的 ready 前崩溃不能返回成功；客户端未收到202不代表没有提交，带key重试须复用原记录。
无幂等key的重复HTTP请求可能产生独立任务，本包不宣称跨请求去重。

| 崩溃位置 | 下次恢复动作 |
|---|---|
| ZIP未完整或descriptor未提交 | 没有可派发记录；未知残留不盲删，不创建ScanRun |
| prepared已提交、registry明确不存在该ID | 不派发；仅可清理严格验证为本descriptor所有的副本和descriptor |
| registry queued已提交、仍prepared | 绑定/输入/profile完整匹配时原子提升ready，再正常派发；不永久卡在prepared |
| ready提交后、唤醒或202到达前 | ready扫描可发现；同key重试复用原任务 |
| queued→running CAS前 | 尚未调用handler，后续仍可正常claim |
| running CAS后，任意handler/阶段CAS之间 | 不重放handler，仅按第7节收敛 |
| A6字节/metadata已写、terminal CAS前 | orphan保持不可见；不发布、不补links、不重放publisher |
| terminal CAS后、清理前 | terminal逐值保持，只清理本任务私有输入/descriptor |

registry I/O或commit结果不确定时，必须保留prepared和输入供核对；不得把异常当作
“肯定没创建”而删除可能已被持久任务引用的输入。not_found必须来自健康registry的明确读取。
prepared与registry是跨文件/SQLite的可恢复协议，不宣称原子enqueue或跨介质事务。

## 7. 派发、恢复与错误收敛

只处理严格合法且与registry身份精确绑定的ZIP descriptor。
缺失、损坏、重复或错绑descriptor：停止对应任务派发，保留原始状态与文件，输出稳定内部诊断；
不根据可疑scan_id修改另一任务，不自动删除或重建。默认继续处理其他合法任务；
底层目录/registry整体损坏则停止dispatcher。legacy无descriptor的queued/running保持原样。

启动持锁后先处理descriptor匹配的既有running，再处理prepared/ready；正常周期处理ready。
不能在同一进程的活动handler仍执行时对它做“中断恢复”。registry始终是公开结果权威来源。

### 7.1 queued

ready、输入与profile验证通过后构造一次性plan，只调用现有worker.run一次。
CAS竞争失败时不执行handler，重读并尊重赢家；不得覆盖cancelled/terminal。
合法绑定但输入缺失/损坏/权限异常或profile失配，可用内部无handler的失败收敛入口：
queued→running/ingestion/5（logical claim）→failed，追加稳定错误，不调用parser/AI/publisher。
这两次CAS保持A3单向约束；ingestion/5表示失败定位，不能表述为已成功解压。
两次CAS之间崩溃则按running中断收敛，允许原因退化为无法确定的worker_interrupted。

### 7.2 interrupted running

在新进程已取得生命周期锁后，读取最后一个完整快照。若running异常含有report_links，
停止该任务恢复并保留原状态供人工核查，不写terminal、不清空事实、不清理输入；
否则收敛会让这些links从不可见变可见，违反A6门禁。正常恢复候选report_links必须为空。
满足此门禁后，以原revision做CAS：

- 有可用分析聚合（components/ai_assets/evidence/findings任一非空）→partial；
- 无聚合→failed；
- 追加 `worker_interrupted`，message=`Worker execution was interrupted.`；
  partial的recoverable=true仅表示已有结果可用，不承诺自动续跑；failed为false。
- 保留所有原事实、errors、身份、stage、progress和started_at；finished_at不早于
  started_at或created_at，必要时取当前UTC与该下界的最大值，不能重置started_at。
- 不调用任一handler或terminal publisher，不读取orphan生成新的ReportLink。
  恢复所得partial可能没有可下载报告，GET仍按原规则返回report_not_ready。
  已有terminal一律不修改，已公开报告照常由原GET校验读取。

### 7.3 重查与停止

只对claim前或恢复CAS前明确的 `registry_busy` 做每周期至多3次尝试（首次加2次重查），
等待0.1秒、0.5秒；仍busy则结束该周期，保持原状态、保留输入，下一周期至少1秒后开始。
这是有界存储重查，不是业务handler retry，也不是跨重启总attempt上限；不新增attempt表。
未知I/O/损坏/权限故障不无限重试，不转成伪终态。claim或CAS结果不确定时先重读，
没有可靠读取结果就停止本任务，不重新调用worker.run。不得自动重放任何曾为running的任务。

ScanError使用 `worker_interrupted`、`dispatch_input_unavailable`、`dispatch_input_invalid`、
`dispatch_profile_disabled`、`dispatch_profile_mismatch`；消息为固定英文短句，不能包含
底层异常、路径、输入文本或凭据。HTTP沿用既有信封与状态映射，内部dispatcher诊断不直透HTTP。

## 8. 清理与隐私

清理只在健康registry明确terminal，或启动时健康registry明确prepared没有对应行时进行。
只允许通过严格验证的descriptor定位其自有basename，使用私有root下no-follow/dirfd操作；
不能跟随符号链接、按glob删除、删除别的任务或用户原文件。先删自有ZIP并fsync，再删descriptor
并fsync；失败保留descriptor供后续仅清理，不能因此重新执行pipeline。
输入已缺失的terminal可完成descriptor清理；疑似篡改的对象保留并诊断，不扩大删除范围。
报告orphan和A2中断workspace留给独立cleanup工作包，不采纳、清除或宣称已解决。

## 9. 独立验收矩阵（I1/I2联合门禁，完整闭合待I2）

Luna使用真实独立OS进程、私有临时目录、手写multipart/动态ZIP、第二SQLite连接、
独立事件管道及kill/restart；不得用线程竞争或实现侧expected/helper替代核心oracle。
断点需以事件/屏障确认，不靠任意sleep猜测。允许无副作用的内部故障注入点，不增加公开API。
fsync顺序通过受控write/rename/fsync故障注入或事件屏障证明，不以文件存在推断落盘顺序；
本机进程kill测试不证明硬件断电、磁盘故障或所有文件系统的持久性。

| ID | 必须独立证明的结果 |
|---|---|
| DZ-01 | 上传/descriptor的权限、basename、digest、大小与目录fsync顺序；未知/重复键和版本失败关闭 |
| DZ-02 | prepared前后、registry提交前后、ready前后逐个kill；只有满足两份持久事实才允许新任务202 |
| DZ-03 | prepared+exact queued+完整输入经重启提升ready并执行；无row只处理自有orphan，不伪造run |
| DZ-04 | ready后丢失唤醒、202后退出：新进程自动发现；真实ZIP经原A2+B1+A4+A6形成诚实partial/rules/70及四格式报告 |
| DZ-05 | 同key同字节（含管理员配置改变）保留原ID/profile/输入；不同字节409；并发提交无第二派发 |
| DZ-06 | 两个独立应用竞争flock，输家不服务不handler；长时间持锁不能靠超时抢占；正常shutdown活动线程结束前不释放锁 |
| DZ-07 | queued claim的CAS只有一个赢家；旧revision不覆盖terminal/cancelled；无descriptor的legacy ZIP/Git逐值不变 |
| DZ-08 | running在claim后、handler返回前后、阶段CAS前后kill：无handler重放；最后durable分析聚合决定partial/failed，恢复候选links为空，身份/阶段/时间不回退 |
| DZ-09 | 用独立计数Provider证明A5已调用但阶段CAS前kill，恢复不再调用；不能声称外部已完成或exactly-once |
| DZ-10 | A6发布后terminal CAS前kill：orphan始终不可见，不publisher、不补links；异常running含links时拒绝恢复，原状态保持不可见；CAS后kill：终态及已公开links保持 |
| DZ-11 | 合法descriptor对应输入丢失/摘要不符/链接/权限异常时零handler、零publisher，合法logical claim后failed；错绑descriptor不改无关run |
| DZ-12 | ai_requested=false保持AI关闭，profile匹配仍正常提升ready；true遇管理员禁用或profile失配零handler失败；同profile实际Ollama不可用沿用A5降级 |
| DZ-13 | 独立SQLite锁使明确registry_busy的claim/recovery CAS仅本周期首次加两次重查，超限不伪终态，释放后继续；不累计跨重启attempt，不对I/O不确定/损坏/权限错误做业务重试，保留输入重读 |
| DZ-14 | terminal后删除失败、ZIP已删descriptor未删的kill窗口只触发清理；恶意/未知文件及其他任务文件保持，配额包含残留且并发不超额 |
| DZ-15 | P0/Schema/sample、六API/OpenAPI、registry v1对象allowlist、A4显式worker、默认关闭模式、A5/A6既有保护集及全量回归通过 |

报告下载oracle必须实际GET并校验正文/摘要；kill后的断言必须新进程读取持久数据。
既有回归通过不能替代这些新门禁；异常路径partial无报告是第7节明确限制，不应改成completed。

## 10. 文件所有权与实施顺序

本规格任务只修改本文件、PROJECT_PROGRESS、AI辅助记录及append-only AGENT_WORKLOG。

未来实现候选白名单（编码开工仍须重新核验）：

- 新增 `backend/app/persistence/zip_dispatch.py`：descriptor严格编解码、原子提交和自有输入清理。
- 新增 `backend/app/pipeline/zip_dispatcher.py`：单线程消费、生命周期锁、恢复和无handler收敛。
- 最小修改 `backend/app/api/service.py`、`zip_scan.py`、`main.py` 与必要`__init__.py`；
  保持现有公开方法兼容，默认关闭路径不变。优先不修改worker.py，直接调用registry公共CAS。
- 新增 `tests/unit/test_a3_durable_zip_dispatch.py` 与
  `tests/security/test_a3_durable_zip_dispatch_independent.py`；必要运行文档与治理记录。

禁止修改 `domain/`、`schemas/`、`examples/`、`scan_registry.py`、Git runtime、
ingestion/scanners/rules、A5实现、A6 store/render、frontend/deploy，以及既有独立测试断言。
若实现无法保持上述边界，先回到本规格审查，不能为了过测试放宽保护代码。

实施按同一规格分两个完整验收点：

1. `A3/A4-3a-I1`：私有descriptor、prepared/ready/幂等协议与输入生命周期，保持默认关闭；
   完成实现测试和Luna独立存储/崩溃窗口门禁，不宣称已有自动恢复。
2. `A3/A4-3a-I2`：lifespan锁、dispatcher、queued恢复、running收敛，关闭DZ-01..15，
   实施与独立全量门禁、不可变提交绑定及Root发布后，才批准ZIP有界运行evidence。

不新增第三方依赖，不安装/调用外部扫描工具或真实模型；实际依赖变化必须另行登记资源。
后续才评估Git接入、lease/heartbeat、可证明安全的业务retry和cleanup，不自动排入本实现包。

## 11. 规格审查记录

GPT-5.6 Sol、GPT-5.6 Terra、GPT-5.6 Luna 已只读复核最终语义并分别批准；
GPT-6 Astra / Root 统一编写与修订，无模型并发编辑本文件或共享日志。
审查关闭项：running异常links不得通过终态变为可见；首个multipart字节前完整配额预留；
prepared匹配后的ready恢复；同key同字节保留原profile；busy只作每周期有界重查。
Root 另核查DZ编号唯一性，未因工具重叠展示删除有效条目。
冻结当时，规格批准仅说明设计门禁通过，代码和动态运行evidence尚未实现；后续I1实际结果见第12节，部署能力仍待后续。


## 12. I1 实现与验收记录（2026-09-05）

证据ID：`EVD-A3-DURABLE-ZIP-STORAGE-001`；实现提交：`272f5cfed49c88b0bea4063b22d3cce5a8a9a6ee`；已推送`feat/a3-durable-zip-storage`并以远端完整哈希核对。

I1新增私有descriptor存储及输入生命周期，内部拆分ZIP candidate构造/提交，复用原registry与
幂等fingerprint。真实HTTP注入入口在multipart首字节前预留配额；无await临界区覆盖文件创建与
reservation绑定，以及prepared→registry→ready提交片段。输入fsync/摘要校验、五字段AI身份、
健康registry限定清理和残留计额已实现。没有新增依赖、数据库对象或公共模型/API。

生产工厂默认`OPENGUARD_ENABLE_DURABLE_ZIP=0`，继续既有BackgroundTasks；精确`1`明确拒绝
启动，非法值也拒绝。I1只能内部显式注入store进行验证，不会执行worker或自动恢复任务。
第3节的完整启用方式留待I2生命周期锁与dispatcher验收后开放。

| 验收层 | 结果 | 边界 |
|---|---|---|
| Terra实现侧 | 16 passed；关联190 passed,1 deselected | 关联集排除原真实Uvicorn用例，完整集另验 |
| Luna独立验证 | 最终29 passed | 动态ZIP/手写multipart、实际OS线程和进程、独立期望，不复用实现unit/helper |
| 并发缺陷闭环 | 首轮19 passed,1 failed；修复后原202断言通过 | 文件创建与预留绑定曾有竞争窗口；只修业务临界区，保留原失败记录 |
| 系统调用与崩溃 | 实际文件inode定位fsync/rename故障；四个kill窗口、新进程SHA与字段绑定 | input_fsynced、prepared_fsynced、registry后ready前、ready_fsynced；不证明硬件断电 |
| Root完整回归 | 952 passed,3 skipped,1 warning | 首次沙箱940 passed,11回环权限失败,3 skipped；受控原命令通过 |
| 冻结兼容性 | OpenAPI与基线完全等值；P0 Schema/sample、保护目录、编译检查通过 | 六API、registry v1、A5/A6及组员代码保持兼容 |
| 前端基线 | TypeScript与Vite生产构建通过 | 前端未改，仍不代表真实Web联调完成 |

三个skip属于原有可选门禁，本轮没有启用真实模型或公网扫描。warning为既有
Starlette/AnyIO弃用提示。复现命令见backend/README.md及上述两份测试文件。

本节只批准DZ矩阵中I1存储/协议子集；不将DZ-01..15整体标为完成。I2生命周期flock、自动消费、
queued恢复、running收敛、handler不重放和报告恢复可见性仍待实现与独立验证。
Git恢复、lease/heartbeat、业务retry和完整orphan清理仍留后续工作包。

## 13. I2 实现与验收记录（2026-09-05）

基线：`2368d91120a72e7bb474ddacfcb72743b9aa02b1`；分支：`feat/a3-zip-dispatcher-recovery`。
证据ID：`EVD-A3-DURABLE-ZIP-DISPATCH-001`；实现提交：`f48108f6da32ea36e6e757a3cd80a2b42baa0767`，已推送功能分支并核对远端完整哈希。
本轮仅实施第10节I2，复用I1存储、registry v1、原worker与A4/A5/A6；无新增公共API、数据库对象或第三方依赖。
生产开关默认0保持旧路径；精确1现在启用单机ZIP dispatcher。I1 unit中“因I2未实现而拒绝1”的阶段性断言迁移为真实生命周期正向验收，默认0和非法值门禁保留；既有独立函数/类AST未变。

固定私有flock覆盖完整生命周期；startup恢复与单线程周期派发分离，shutdown等待worker结束、关闭registry后释放锁。queued恢复复用唯一worker；已有managed running保留事实收敛partial/failed，不重放handler、AI或publisher。不确定CAS隔离、未知I/O停止接单、终态只补健康清理。Git恢复、多机、lease/heartbeat、业务retry不在本包。

| 独立门禁 | 实际证据 |
|---|---|
| DZ01–03 | 真实dispatcher持锁/ready消费/terminal清理；prepared恢复；descriptor摘要错绑保持queued且不dispatch |
| DZ04–05 | 无notify周期恢复；四格式HTTP下载；重复multipart单run并保留原profile |
| DZ06–07 | 第二dispatcher锁互斥；真实dispatcher后的fork子不延长父锁；OS barrier下claim/cancel/terminal赢家；无descriptor的ZIP/Git逐值不变 |
| DZ08 | 四个真实kill窗口：claim CAS后、handler返回前、stage CAS后、handler返回但下次CAS前；新进程精确核对事实与零重放；异常running links阻断 |
| DZ09–10 | 既有A5公开apply_ai_remediations路径+fsync调用计数重启仍1；publisher/terminal CAS前后kill、orphan不可见、链接保留与四格式真实GET |
| DZ11–12 | missing/digest/perms/symlink输入零handler；原timeout、disabled和不兼容provider；腐坏descriptor仅诊断 |
| DZ13 | queued/running恢复三次busy及冷却；未知claim I/O隔离不重试。修复前第三至第四CAS约0.076秒，修复后第三至成功CAS为1.008917秒，满足至少1秒 |
| DZ14–15 | ZIP删除后descriptor未删kill/restart只补cleanup并保留unknown；默认0/schema兼容；真实create_default_app、Uvicorn、multipart POST/GET链路 |

验收结果：Terra unit **28 passed**；Luna独立 **70 passed,2 warnings**；Root受控完整 **1005 passed,3 skipped,2 warnings（51.04秒）**。开工I1基线45项通过。Root核对OpenAPI与开工快照完全相同，Schema等值、sample有效、编译、冻结目录、原独立AST和append-only前缀通过。
独立首轮5失败/23通过涉及错误终态预期、事件重复等待与观察时机；按冻结语义修正fixture/oracle，未弱化产品断言。后续真实running恢复busy缺陷单独保留原始失败，Terra增加周期前冷却后独立及全量通过。沙箱loopback PermissionError保留，受控环境原用例通过。
三个skip是既有可选真实模型/公网门禁；本轮不新增真实模型或公网证据。两个warning分别为Starlette/AnyIO弃用和刻意fork测试的Python多线程fork提示；不证明一般fork安全或硬件断电恢复。

可演示：durable ZIP真实HTTP queued恢复后依赖纵切与阶段报告；普通输入仍为partial/rules/70。中断running仅事实收敛，可能没有报告。不能外推完整许可证链、真实Web、部署、A6全量交付或竞赛成品。
下一任务回到原始V1.0第15节P0 DoD：A4消费组员真实scanner/SPDX/AI资产公共输出。不得自动扩展Git恢复、lease或业务retry；产品P1/P2不进入本轮。
