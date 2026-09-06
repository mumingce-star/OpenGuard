# 前端任务消费契约 v2（待团队确认）

这是前端 adapter 的拟定消费契约，不是已经获后端确认的接口，也不是后端实现说明。
本轮只改前端，不修改 FastAPI、数据库、扫描器、规则或 AI 服务。

## 请求

| 操作             | 请求                                                 | 预期响应                            |
| ---------------- | ---------------------------------------------------- | ----------------------------------- |
| 仓库访问校验     | POST /repositories/validate，JSON {url}              | JSON {accessible:true} 才显示可访问 |
| 创建 GitHub 扫描 | POST /scans，JSON {kind:"github",url,scopes}         | 完整 Scan，通常 queued              |
| 创建 ZIP 扫描    | POST /scans，multipart file 与 scopes（JSON 字符串） | 完整 Scan                           |
| 恢复/刷新任务    | GET /scans/:scanId                                   | 该编号的完整 Scan                   |
| 人工处理状态     | PATCH /scans/:scanId/risks/:riskId，JSON {handling}  | 2xx JSON 或 204；随后重新读取快照   |

创建任务携带 Idempotency-Key。前端禁用重复提交，同一次输入失败重试保留 key；输入改变重新生成。
服务端必须实现实际幂等去重，前端按钮锁不替代服务端保证。页面刷新不持久化未确认创建请求的 key，响应丢失后的任务恢复需要服务端支持。

GitHub 仅做 https/github.com/owner/repo 格式预检，不靠格式校验声称可访问。
当前 UI 只面向公开仓库；私人仓库的认证方案需单独确认。
ZIP 仅检查扩展名、非空和已配置大小；类型识别、解压安全、路径穿越/压缩炸弹防护、超时必须由后端完成。

## Scan 类型

权威前端定义在 src/types/domain.ts；src/services/scans.ts 的 validateSnapshot 为运行时边界。
完整结构可以用标准演示导出的 JSON 参考，但 API 不得把演示内容当真实扫描结果。

必需字段：

- id、mode（api）、project、input、createdAt、finishedAt（可 null）。
- status：queued / running / completed / failed / partial。
- stages：阶段名称数组；stageIndex：已完成阶段数，0 到 stages.length。
- error：字符串或 null。partial/failed 应提供可呈现的错误原因。
- completeness 必须为 full；snapshotVersion 必须为字符串。
- resources、risks、evidence 为完整数组，允许空数组但不允许缺失。
- queued/running 的数组可以为空，UI 不把它们当最终结果；completed 必须完成全部阶段。
- 部分完成任务可展示已获得结果，不把它描述成全面成功。

## 关联与空值

- 每种实体的 id 在其数组中唯一，Risk.resourceId 必须指向现有资源。
- Risk.evidenceIds / Resource.evidenceIds 可以引用尚未提供的证据，UI 显示“待补充”。
- Resource.type 为 Package / Model / Dataset / API / Service / Asset。
- license、origin、version 可为 null；licenseStatus 为 confirmed / review_required / unknown。
- severity 为 critical / high / medium / low。
- handling 为 open / reviewing / resolved；verification 为 unverified / passed / failed，二者互不代替。
- fact / conclusion / remediation 可以为 null。
- ai.status 为 ready / failed / unavailable；ai.text 可为 null。
- Evidence.kind 为 code / license / rule；label、source 必填；text 可为 null。
- Evidence.path / url 可缺省；startLine 若存在为正整数，highlightLines 为真实行号数组。

缺省未知字段与非法枚举不能自动填成“成功”。契约不符显示错误而不是渲染空白页。
外部文本经 React 文本节点显示，不使用 dangerouslySetInnerHTML。来源链接仅接受无嵌入凭据的 http(s) URL；这不等于对外部网站可信性的背书。

## 统计与导出

所有卡片、筛选计数和报告共用同一完整快照：
资源总数=resources.length；风险总数=risks.length；待处理=handling!=resolved；
许可待确认=licenseStatus!=confirmed（包含未知与待复核）。
处理状态不会改变严重度；统计不随筛选减少。

若真实接口分页，后端需提供完整汇总和分页导航，或者 adapter 拉取完整快照。本版本拒绝 completeness 非 full 的分页片段，不伪装总数。
大项目不宜无限堆入内存；本轮合成数据只验证交互，下一步与后端约定分页和图谱规模边界。

报告 JSON 保存任务标识、时间、模式、状态、快照版本、资源/风险/证据及派生 summary。
资源 CSV 仅包含当前筛选结果并防御公式注入。
打印/PDF 使用浏览器打印流程，不声称直接上传或持久化报告文件。

## 错误、刷新和安全

- 请求超时 15 秒；轮询为 API 2.5 秒、演示 0.5 秒，仅进行中的任务轮询。
- 页面隐藏停止后续轮询；回到页面重新查询；切换任务/模式中止旧读取。
- 404、网络/CORS、非法快照有错误和重试；不静默切换演示。
- 服务端错误正文不直接回显，避免泄露堆栈/敏感信息。
- 不内置认证 Token；CORS、身份认证、权限隔离、限流和审计需后端落实。
- 尚未实现 SSE、取消、真实复扫和历史比较；UI 不伪造这些操作的成功状态。

## 联调待确认

1. 路径、错误码/错误 envelope、身份认证方式、CORS 与部署前缀。
2. Scan DTO 与仓库现有 schema 的映射、全量与分页边界。
3. 任务阶段语义，partial 的已完成阶段与错误字段。
4. ZIP 上限与服务端校验；幂等 key 有效期与“创建响应丢失”恢复。
5. 风险处理写入权限、真实复扫回填 verification、证据原文权限和稳定地址。
6. 覆盖范围、历史比较和扫描取消由哪组后端字段支持。

浏览器测试通过拦截请求验证前端约定，不能当作实际后端扫描或服务联调证据。
