# A02 — Scan History Backend

Owner: 项目负责人 / A。Base: `integration/p1@d12bfc8a34b76e6cb9134e27e785f2634bc85d0c`。

本任务只新增 History GET；A03 Diff与其它P1功能未实现，未部署生产。契约唯一源为[Workspace Contract](../spec/p1-workspace-contract.md)。本次只按负责人授权增加q语义澄清，Contract版本1.0与所有Frozen Schema保持不变。

## API与字段来源

`GET /api/v1/scans?cursor=&limit=20&status=&source_type=&q=&project_key=` 返回 `{schema_version:"1.0",items,next_cursor}`。limit为1–100整数；status/source_type按原枚举精确匹配，project_key按投影key精确匹配。无过滤时包含queued/running/completed/partial/failed/cancelled。

独立实现：`backend/app/p1/models.py`、`history.py`；main.py仅新增GET和应用内存游标签名key。旧POST/detail/Assessment路由不变。无新DB/表/迁移，registry文件未修改。

- scan_id/project.revision/status/stage/created_at/finished_at来自原ScanRun；UTC以Z输出。
- component_count/ai_asset_count/finding_count来自事实数组，summary保留原分项。
- input_hash为已有input_digest，Git URL摘要不称源码hash；inventory_hash允许null。
- provenance.source_refs的facts_hash复用assessment.engine.facts_digest，registry_revision为读取版本。
- latest_assessment仅调用现有AssessmentStore.latest；无记录或未配置assessment服务时null。已配置存储读失败返回503 upstream_unavailable，不伪装成无记录，也不修复或重建评估。

## 身份与公开source

复用P0 URL policy验证已存Git source，无DNS或网络调用；GitHub owner/repo casefold，去尾.git和/生成canonical_github_repo_v1，不含revision。其它来源保守scan_only；ZIP即使同名同hash也按scan_id独立。

ZIP API的原source可能为staged_name，不是用户授权公开的上传名，因此本实现不返回或搜索它，返回固定`ZIP upload`标识。local和无法安全公开的Git source返回`Source withheld`。这些固定提示不参与source搜索，不能从搜索命中推断隐藏路径。P0本身拒绝绝对local路径；History仍做防御性投影，不修改事实。project.name若呈现路径形态（含/或反斜线）也不参加q搜索。

## q与分页

q先strip，再Unicode casefold，空值视为未提供。仅对project.name与安全投影后的公开Git source做literal substring。无regex/fuzzy/模型；不搜索证据、finding、assessment、AI、报告、metadata、ID或revision。

复用SQLiteScanRunRegistry.list_runs，每次最多读100条，在服务端逐页筛选，收集limit+1个命中确定next_cursor。cursor锚点为最后实际返回记录；下一页从该锚点继续，避免跨底层页的稀疏过滤漏项。排序保持created_at DESC/scan_id ASC。

cursor为应用私有HMAC签名的URL-safe opaque token，内部绑定版本、锚点/时间、sort和规范化filters摘要。不含明文q、路径或签名密钥。客户端只能原样传回；不应依赖编码结构。篡改、非法、失效锚点、不同filters或应用重启后使用旧cursor均400 cursor_invalid；存储I/O故障503，不伪装成cursor错误。limit不属于筛选语义，允许翻页时修改页大小。

没有新增密钥文件或DB写入：签名key在create_app时生成，只保存在应用内存。当前单实例部署适用；跨多进程或重启不承诺游标可复用，返回明确400后客户端刷新首屏。分页不是数据库快照，新记录可通过刷新第一页看到。

## 无副作用与隔离验收

History只读取registry/assessment store，不调用扫描、工具、Detector、Rules重跑、Assessment生成、Qwen/Chat、metadata、Report或Task创建。测试通过写入方法/进程/网络/模型入口禁用及查询前后数据库文件哈希和registry revision相等检查。无真实Git扫描，无生产端口操作。

验证命令（既有Python3.12开发环境，无新增生产依赖）：

```sh
PYTHONPATH=backend python -m pytest -q -p no:cacheprovider tests/unit/test_p1_history_api.py
PYTHONPATH=backend python -m pytest -q -p no:cacheprovider tests/unit/test_p1_contract_schema.py tests/unit/test_p0_domain_models.py tests/unit/test_a3_scan_registry.py tests/security/test_a3_scan_registry_independent.py tests/unit/test_a3_fastapi_api.py tests/security/test_a3_fastapi_api_independent.py tests/unit/test_v4_assessment_core.py tests/unit/test_v4_assessment_api.py tests/test_assessment_review_groups.py
```

最终新增History测试24 passed；P1 Schema42 passed；上述既有P0回归235 passed。实际执行分批：初次组合297 passed、1个回环端口沙箱权限错误；该项测试原样在获准的临时回环环境重跑1 passed；随后增加3个History测试，History最终24 passed。没有删除失败测试。唯一warning为既有Starlette/AnyIO弃用提示。

两项旧OpenAPI“只能POST”的测试只更新为明确允许新增GET，保留其它路由集合校验。额外对完整OpenAPI执行基线/当前语义对比：移除唯一新增GET与新增类型后必须与基线完全相等，原POST/detail/Assessment及已有components逐项相等。

## OpenAPI semantic diff留证

- 基线SHA256：`79534416ac792d8a70288c7af48cc5fad024cb91de05912150fe8c74ccfc45bf`
- A02 SHA256：`d31c12db6b8c7689dcda4af00f01b73b56998d4845b12d720e112ab363f88997`
- paths新增：无；既有`/api/v1/scans`新增GET。
- 新增schema：P1AssessmentRef、P1GithubIdentity、P1HistoryPage、P1HistoryProvenance、P1Producer、P1ScanHistoryItem、P1ScanOnlyIdentity、P1ScanRef、SourceType。
- 其它语义变化：无。生成方式为独立导入基线与当前create_app(None,assessment_service=object()).openapi()；未启动lifespan或HTTP服务。

本机完整对比记录保留在`output/manual-fixes/a02-history-20260913/openapi-comparison.json`，不作为运行依赖。

## 限制与下一步

服务器筛选逐页读取，极大历史集合的稀疏搜索最坏需遍历全部历史；本轮没有宣称性能目标达标，也不加History表/索引迁移。没有前端页面或生产部署验收。工作完成后只推送本人feat/p1-history-diff，等待负责人Review；不merge integration/p1，不操作cz/xzb分支，不开始A03。
