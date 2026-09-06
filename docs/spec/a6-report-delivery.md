# A6-1 报告安全持久化与只读下载

状态：P0 实现纵切；由 A6-2 Pipeline publisher 消费
范围：项目负责人 A6；不包含扫描分析组员 B5 或前端接线

## 1. 目标

A6-1 把 A6-0 已验证的内存 `ReportArtifact` 变成可在后端重启后继续读取的私有报告，并保持冻结的六路由 API 不扩张：

1. `ReportArtifactStore.publish()` 显式渲染并持久化一个终态 `ScanRun` 的指定格式；
2. 发布返回 P0 `ReportLink`，其中只有相对下载定位、SHA-256 和 UTC 生成时间；
3. `GET /api/v1/scans/{scan_id}/report?format=...` 默认返回该 `ReportLink`；
4. 客户端只读请求 `ReportLink.href`，即同一路径加 `download=true`，取得经过摘要复核的附件字节。

GET 不生成、覆盖或修复报告，也不改变 SQLite。A6-2 已由 Pipeline 终态 publisher 显式调用本接口；本纵切继续提供经过测试的持久化和 HTTP 消费边界。

## 2. 存储契约

- 报告根目录必须是当前进程用户拥有的真实目录，权限不得向 group/other 开放；默认应用创建 `data/reports` 为 `0700`。
- 每个已校验 `scan_id` 使用一个 `0700` 子目录；内容和 metadata sidecar 均为当前用户拥有的 `0600` 普通文件，拒绝符号链接、特殊文件和权限漂移。
- 内容文件名由 `format + SHA-256` 派生，metadata 是格式级发布提交点。内容先 `fsync` 并原子替换，metadata 后 `fsync` 并原子替换；首次中断不会产生可见报告，更新中断仍保留上一份已提交报告。
- metadata 固定为 `openguard.report-artifact` v1，只保存 `scan_id`、格式、媒体类型、安全下载名、字节数和完整 `ReportLink`；不保存主机绝对路径、凭据或报告之外的用户数据。
- 每次读取重新验证目录/文件类型、owner、权限、inode、长度、metadata 精确字段、公开定位和内容 SHA-256；缺失提交点为 `not_found`，已提交对象不一致为 `corrupt`，均不返回部分字节。
- 单份报告上限为服务端 `16 MiB`，调用方不能提高；A6-1 只使用标准库，不新增第三方依赖。

## 3. HTTP 契约

既有路径与默认响应保持兼容：

```text
GET /api/v1/scans/{scan_id}/report?format=html
  -> 200 ReportLink

GET /api/v1/scans/{scan_id}/report?format=html&download=true
  -> 200 report bytes
```

下载响应使用固定安全文件名，并包含：

- `Content-Disposition: attachment`；
- `Content-Digest` 与 SHA-256 `ETag`；
- `X-Content-Type-Options: nosniff`；
- `Cache-Control: private, no-store`；
- 限制脚本、外部资源、表单和基地址的 CSP。

状态尚未就绪或该格式没有登记 `ReportLink` 时使用 `409 report_not_ready`；一旦 SQLite 已登记链接，内容缺失、链接与 metadata 不一致、存储损坏、权限漂移或 I/O 失败统一映射为脱敏的 `500 internal_error / report_storage_failure`。不向响应写入物理路径、异常正文或损坏内容。store 中存在但未被 `ScanRun.report_links` 登记的内容不可通过 API 读取。

## 4. 阶段性结果与 B5 边界

`partial/rules/70` 是合法输入。它持久化和下载的仍是 A6-0 阶段性报告：保留 `rules_stage_not_connected`，许可证、义务、风险和 AI 建议没有真实事实时保持缺失或待核验，空 finding 不表示合规通过。

A6-1 不新增、替代或模拟 B5 许可证义务规则，不修改组员 B1-B7、P0 Domain/Schema/sample、SQLite scan registry 状态机、A2-A5、Pipeline 或前端。完整许可证报告仍必须等待 B5 的真实、可验证结果。

## 5. 验收范围

- 四种冻结格式的内容、媒体类型、文件名、SHA-256 与 `ReportLink` 一致；
- 同内容重复发布幂等且保留首次生成时间；
- 私有权限、重启读取、内容/metadata 篡改、缺失文件和 symlink 失败关闭；
- metadata 原子提交点及失败更新保留上一已提交版本；
- FastAPI 元数据、只读下载、安全响应头、稳定错误和方法边界；
- 下载前后文件时间不变，证明 GET 未触发写入；
- `partial/rules/70` 的诚实披露不退化；
- P0 Schema、组员代码和既有 A2-A6-0 行为无回归。

复现：

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a6_report_exports.py \
  tests/unit/test_a6_report_delivery.py \
  tests/unit/test_a3_fastapi_api.py
```

## 6. 下一纵切

A6-2 已在 Pipeline 首次终态 CAS 前显式调用 publisher，并绑定四种 `ReportLink`；报告正文投影掉 delivery links 以避免内容摘要自引用，API 中的最终 `ScanRun` 是链接权威来源。前端真实下载接线仍由前端组员完成。最终匿名化、10MB 技术报告 PDF 和作品材料审计仍由 S7/Luna 的材料门禁处理。
