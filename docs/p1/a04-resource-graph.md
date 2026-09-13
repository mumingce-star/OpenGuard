# A04 — Resource Graph Backend

Supporting implementation note，不是第二份 Contract。权威为 `docs/spec/p1-workspace-contract.md` 的 Frozen V1 与负责人批准的 A04 clarification，Contract Version 1.0，正式 Schema 未修改。

## API 与请求

`GET /api/v1/scans/{scan_id}/graph` 只投影已存储 ScanRun；输出 `ResourceGraphView 1.0`、`formal=false`。重复 query 参数传数组；不支持 CSV。两个数组去重排序后按交集选资源；显式 ID 必须先在当前 scan 中存在。未知/空白/非法大小写 kind、任意未知 query 返回 400 invalid_argument，不回显输入。ID 存在但 kind 排除是合法 project-only filtered 图；无 filter 是 all。

completed/partial 返回 200；queued/running 为 409 not_ready；failed/cancelled 为 409 not_comparable；不存在 scan 为 404；registry 不可用为 503。无分页。

## 节点与事实边

七节点为 project、component、ai_asset、license_observation、evidence、finding、obligation。节点 ID=`scan_id:kind:source_id`；保留原 source ID。名称来自已有事实；Evidence 标签只用 kind，不公开 locator、内部路径或 URL 内容。

| 唯一允许边 | 原事实 pointer |
|---|---|
| PROJECT_HAS_RESOURCE | /components/i 或 /ai_assets/i |
| RESOURCE_HAS_LICENSE_OBSERVATION | /components/i/license_expression_id 或 AIAsset 同字段 |
| RESOURCE_SUPPORTED_BY_EVIDENCE | resource/evidence_ids/j |
| RESOURCE_HAS_FINDING | /findings/i/resource_id（类型由已校验事实对象确定） |
| FINDING_SUPPORTED_BY_EVIDENCE | /findings/i/evidence_ids/j |
| FINDING_REFERENCES_OBLIGATION | /findings/i/obligation_ids/j |
| LICENSE_HAS_RULE_OBLIGATION | /obligations/i/license_expression_id |

每条边至少一个 SourcePointer，使用原数组索引、正确 scan_id；独立测试解析 pointer 并核对值与端点。边 ID 使用 scan/type/source/target/source_refs 的规范 JSON SHA256 前缀，非随机。节点按 kind/source_id 排序，边按 type/source/target/id 排序。

## Closure、容量与覆盖

all 包含已有七类事实，包括未绑定 license/evidence；无依据不创建边。filtered 从选中资源向外保留 project、显式 license/evidence、关联 finding、finding 的 evidence/obligation、义务所需 license 及其规则义务。共享端点单节点、多边；不沿共享节点反向拉回未选 resource/finding，不悬空、不推测依赖或共现。

默认 `app.state.p1_graph_max_nodes=20000`、`p1_graph_max_edges=60000`，配置不写入 Schema，不改变扫描限额。完整闭包计数后超限整请求 413 graph_capacity_exceeded；Graph 专用错误 DTO 返回 count_basis=actual、node_count、edge_count、configured_capacity，保留标准 error 外壳，不放宽旧 P0 ErrorBody。没有截断或半图。等于上限允许；可缩小 filter。

view_complete=true 仅表示选中已有事实投影完整。partial 的 scan_gaps 保留已有错误 code 的安全摘要，缺少 code 时为 scan partial；不输出原始错误 message，不宣称全仓库完整。counts 等于数组长度。

## 权威与只读

License Observation 不是授权；Root License 不传播到无显式引用的资源；Finding 不是确认违规；义务被检测不代表已履行。Graph 不是 Formal Assessment，不读取 Assessment，assessment_refs=[]。不执行扫描器、仓库代码、Git/ZIP、模型、联网、metadata、Task 或报告，不写数据库、不迁移历史。

provenance 使用既有 facts_digest 和 ScanRef，绑定规范 filter、算法 resource-graph/1.0、capacity。view_id 和 parameters_hash 不包含 generated_at。P0 ScanRun 原有跨引用验证仍生效，不新增事实或更改原事实。

## 验证与证据

最终相关回归：430 passed，0 failed，0 skipped，1 条既有 Starlette/AnyIO deprecation warning。其中 A04 42（14 unit + 28 independent）、A02 24、A03 67、Frozen Contract 42、P0/registry/API/ZIP/assessment 255。集合不重复相加。

测试覆盖七边及 pointer 值、共享端点隔离、未知/逗号/重复/空白 filter、17项批准语义、状态、Frozen HTTP Schema、容量等于/超过及缩小 filter、稳定 ID、数据库文件 hash/registry revision 不变、禁止写入/子进程/Assessment 读取。原 P0 路由集合测试仅增加 Graph GET 预期，原路由断言保留。

OpenAPI 与基线 `5ad3b9622af444086023514e6a4fe8c3572be98f` 隔离导入比较：12→13 paths；只新增 Graph GET、其 query/Graph DTO/专用413类型，所有旧 methods 和 schemas 精确一致。

本机保留证据目录 `output/manual-fixes/a04-graph-20260913/`（ignored，不提交）：regression-final.log/xml、openapi-comparison.json、performance.json、对应只读核验脚本。初次测试样例引用错误与容量 DTO 接线失败日志保留；最终回归通过，不掩盖中间失败。

## 性能与限制

合成已验证 ScanRun、内存 registry，仅测投影+facts hash，不含 DB/HTTP/浏览器。100资源（105节点/300边）：首次1.161ms，重复1.027/0.977/0.997ms；500资源（505节点/1500边）：5.155ms，5.269/4.942/5.422ms；2000资源（2005节点/6000边）：29.928ms，21.159/20.871/30.787ms。不是生产 p95，不证明前端图渲染<1s。索引/集合构图加稳定排序；完整图仍需内存，capacity 检查不等于操作系统硬内存限额。

本次没有前端、生产部署、真实重扫或模型调用；未完成集成、UI/浏览器和生产验收。A05 未开始。仅发布负责人 feat/p1-graph-api 待 Review。

## Review 操作

在隔离测试环境对一个已存储 completed/partial scan 调用上述 GET；再添加重复 resource_ids/resource_kinds 检查去重和 filtered closure。查询未知 ID 应400；以 component ID 配 ai_asset kind 应得到 project-only。查看 source_refs 与原 ScanRun 对应，不用 Graph 判断商业授权。本轮不要求在生产网页点击不存在的新图页面。
