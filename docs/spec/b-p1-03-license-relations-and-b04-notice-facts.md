# B-P1-03 License关系与 B-P1-04 NOTICE内容事实

本文件是 [P1 Frozen Contract](p1-workspace-contract.md) 的后端B实施说明，不新增公共API或第二份权威Contract。

## 1. Ownership

后端B负责从已经受控读取的来源产生确定、可追溯、保守的事实：subject identity、原始license声明、LICENSE/NOTICE/copyright关系、authorization状态、Evidence、gap和Report草稿行。

后端B不负责外部网络、metadata sidecar、公共API、不可变NoticeDraft、ReportV2Snapshot、下载、前端、部署、独立验收或法律适用性结论。NoticeDraft快照/API和Report绑定属于A/Root；Sol审核语义；Luna独立验收；xzb消费数据。

## 2. 状态语义

- `text_observed`：只证明固定字节中观察到许可证文本或标题，不证明它适用于整个项目或特定分发方式。
- `provider_declared_unverified` / `declared_unverified`：只证明provider字段值被观察，不证明许可证原文、权属或授权。
- `authorization_status=pending`：visibility、gated、revision和license label均不得将其提升。
- `applicability=pending_review`：NOTICE存在、缺失或许可证名称都不能自动确定具体义务是否适用。
- `gap`：缺证据或解析不足，不等于违规；`GAP_NOTICE_FILE_NOT_OBSERVED`只表达未观察到独立NOTICE文件。
- `license_expression_id=null`：B03/B04不自动产生正式许可证表达式。

## 3. Evidence与hash

每条Evidence必须区分：

- `source_file_sha256`：仓库文件、provider fixture或完整归档的字节hash；
- `container_sha256`：存在容器时的完整归档hash；
- `selected_content_sha256`：被引用文件、归档entry或JSON Pointer值的hash；
- `selected_json_pointer`：仅JSON值选择使用；
- `captured_at`、producer/version、source revision和稳定locator。

不得使用一个未注明粒度的`content_sha256`同时表示归档、entry和JSON字段。

## 4. Facts与rows

`facts`是唯一结构化来源。`report_v2_rows`必须由facts确定性生成，并至少逐项保持：subject fact引用、authorization、空expression集合、观察强度、Evidence集合和gap集合。展示文案不是判定接口，消费者不得解析自然语言恢复机器状态。

缺少用途或团队修改证据时必须输出“未由本事实包证明”，不得把计划、依赖scope或仓库位置伪装成许可证证据。

## 5. 验收门禁

1. Schema Draft 2020-12通过，ID唯一，所有引用闭包；
2. v1来源文件和固定commit blob分别绑定SHA-256；
3. repository、archive entry、provider JSON Pointer三种hash粒度均有正例；
4. 所有authorization保持pending，所有正式expression为空；
5. relationship的gap/evidence/applicability不变量通过；
6. facts与rows逐字段等价；
7. 缺NOTICE不自动变违规，provider label不自动变授权；
8. 生成器重复执行字节相同，不访问网络、不启动服务。

当前离线实现位于 `tests/fixtures/notice-license-facts-v2/`。它是提供给A线NoticeDraft实现的稳定输入，不是NoticeDraft本身。
