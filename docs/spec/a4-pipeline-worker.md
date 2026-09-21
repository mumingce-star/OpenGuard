# A4-0 单进程 Pipeline Worker 冻结规格

状态：`FROZEN-FOR-IMPLEMENTATION`  
责任：Sol 冻结；Terra 实现；Luna 独立验证；Root 发布  
依赖：P0 `ScanRun` v0.1.1、A3-0 `SQLiteScanRunRegistry`

## 1. 目标与证据边界

A4-0 为项目负责人主线提供最小、可调用的任务编排纵切：调用方显式传入一个完整阶段计划，worker 以 A3 revision/CAS 认领 durable `queued` 任务，按固定顺序持久化阶段和进度，并最终生成合法的 P0 terminal `ScanRun`。

本纵切只证明单进程、单次显式调用下的编排与失败定位。阶段 Adapter 可以是测试 stub，也可以在后续接入组员提供的扫描模块；A4-0 不实现这些模块内部，不自动消费 A3 API 队列，不得把 stub 完成结果描述为真实扫描结果。

## 2. 公共内部接口

实现位于 `backend/app/pipeline/`，对后端内部导出：

```python
class PipelineError(RuntimeError):
    code: str

class PipelineStageFailure(RuntimeError):
    code: str
    public_message: str
    recoverable: bool

@dataclass(frozen=True)
class PipelineStep:
    stage: ScanStage
    handler: Callable[[ScanRun], ScanRun]

@dataclass(frozen=True)
class PipelinePlan:
    steps: tuple[PipelineStep, ...]

class ScanPipelineWorker:
    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...

    def run(self, scan_id: str, plan: PipelinePlan) -> StoredScanRun: ...
```

`PipelineError` 只对调用方暴露稳定 `code`，异常链必须为 `None`。A4-0 冻结的调用错误码：

- `pipeline_invalid_argument`：`scan_id`、plan、step、stage、handler 或 clock 不合法；
- `pipeline_not_claimable`：任务不存在、不是 `queued`，或已由其他执行者认领；
- `pipeline_registry_failure`：非认领竞争的持久层失败；
- `pipeline_state_conflict`：执行途中 revision 被其他执行者改变，且最新状态不是 `cancelled`。

这些是后端内部错误，不新增或修改 A3 HTTP 错误信封。

## 3. 固定阶段与进度

一个合法 `PipelinePlan` 必须精确包含下列七个阶段一次，不能缺失、重复、换序或包含 `queued/completed`：

| 顺序 | `ScanStage` | 进入阶段时持久化进度 |
|---:|---|---:|
| 1 | `ingestion` | 5 |
| 2 | `inventory` | 15 |
| 3 | `scan` | 35 |
| 4 | `normalize` | 55 |
| 5 | `rules` | 70 |
| 6 | `ai_assist` | 85 |
| 7 | `report` | 95 |

成功终态必须为 `status=completed`、`stage=completed`、`progress=100`。

## 4. 执行协议

1. `run()` 先读取 `scan_id`；只有 `queued/queued/0` 可以认领。
2. 认领以当前 revision 做 CAS，一次写入 `running/ingestion/5` 与唯一 `started_at`。两个并发调用最多一个认领成功；失败者不得执行任何 handler。
3. worker 按表中顺序执行。每个 handler 开始前，先以 CAS 持久化该阶段和固定进度；首阶段的该写入就是认领写入。
4. handler 只接收当前已持久化的 P0 `ScanRun`，返回新的完整 `ScanRun` 候选。worker 保留其聚合结果，但强制覆盖运行控制字段为当前 `running/stage/progress/started_at`，并令 `finished_at=None`；A3 注册表继续负责 project/id/created_at 等不可变字段和 P0 引用/摘要校验。
5. handler 成功后，以当前 revision CAS 持久化候选。若候选与当前 canonical 快照相同，允许 A3 no-op 不增加 revision。
6. 最后一个 handler 成功后，以 CAS 写入 `completed/completed/100` 和 `finished_at`；`started_at` 不得改变。
7. clock 必须返回 offset-aware UTC `datetime`，且认领时间不得早于 `created_at`，完成时间不得早于 `started_at`。不合法时在首次写入前以 `pipeline_invalid_argument` 失败。
8. A4-0 不恢复既有 `running` 任务，也不重试 handler；租约、心跳、超时、孤儿回收和崩溃恢复留给 A4 后续工作包。

## 5. 失败、partial 与取消

- Adapter 可抛出已经校验的 `PipelineStageFailure`。其 `code` 必须匹配 `[a-z][a-z0-9_]{0,99}`，`public_message` 必须满足 P0 `ScanError` 的长度和脱敏约束；worker 将当前真实阶段写入 `ScanError.stage`。
- Adapter 抛出的其他异常、返回非精确 `ScanRun`、返回不符合 P0/A3 约束的候选，统一转换为 `code=pipeline_stage_failed`、`message=Pipeline stage failed unexpectedly.`，不得泄露原异常文本、路径、URL、凭据或 traceback。
- 只有同时满足以下两项才写 `partial`：Adapter 明确声明 `recoverable=True`；当前最后一次已持久快照至少含一个 `Component`、`AIAsset`、`Evidence`、`RiskFinding` 或 `ReportLink`。否则写 `failed`，且新错误的 `recoverable=False`。
- `partial/failed` 保留当前失败阶段与固定进度，追加结构化错误并设置 `finished_at`；不得伪造 `completed`。
- 若阶段写入或终态写入发生 revision conflict，worker 重新读取一次。若最新状态为 `cancelled`，直接返回该 durable cancelled 快照；否则抛 `pipeline_state_conflict`，不得覆盖赢家。
- 非 revision conflict 的 registry 失败映射为 `pipeline_registry_failure`；任务可能保留在最后一次 durable 状态，调用方可据 `scan_id` 查询。

## 6. 冻结验收用例

### 正向

- `POS-A4-001`：七个 handler 按固定顺序各执行一次，queued 最终为 completed/100。
- `POS-A4-002`：handler 返回的合法 P0 聚合数据跨阶段、终态和 SQLite 重开后保持。
- `POS-A4-003`：首写即 running/ingestion/5，`started_at` 只设置一次，各阶段/进度单调。
- `POS-A4-004`：有可用结果后的显式 recoverable failure 形成 partial，错误定位真实阶段。
- `POS-A4-005`：执行途中已被外部取消时返回 cancelled，worker 不覆盖赢家。

### 负向

- `NEG-A4-001`：缺失、重复、错序、非法阶段或非 callable handler 的 plan 在任何 handler 执行前拒绝。
- `NEG-A4-002`：不存在、running、completed、partial、failed、cancelled 任务均不执行 handler。
- `NEG-A4-003`：并发认领最多一个 worker 执行 handler。
- `NEG-A4-004`：无可用结果的 recoverable failure 必须降为 failed。
- `NEG-A4-005`：未知异常文本含绝对路径、URL 或 secret 时，durable error 与抛出错误均不泄露。
- `NEG-A4-006`：返回非 `ScanRun` 形成脱敏 failed，不使任务卡在 running。
- `NEG-A4-007`：Adapter 篡改任务/项目不可变字段形成脱敏 failed，篡改值不落库。
- `NEG-A4-008`：非取消的执行中 CAS 冲突不覆盖赢家，并返回 `pipeline_state_conflict`。
- `NEG-A4-009`：不合法 clock 在首次写入前拒绝，任务保持 queued。
- `NEG-A4-010`：非 revision conflict 的 registry 故障不执行后续 handler、不泄露底层上下文。

## 7. 发布声明

A4-0 evidence 只能表述为“本机 macOS/POSIX、CPython 3.12、SQLite、单进程显式调用、注入 Adapter 的 durable Pipeline 编排纵切”。在真实 A2/Git 摄取、B1-B7/规则/AI/报告 Adapter、后台消费、Linux 隔离与端到端 Web 流程完成前，不得声称 API 创建后会自动扫描、已生成真实许可证结论、具备 exactly-once 或完整参赛产品能力。
