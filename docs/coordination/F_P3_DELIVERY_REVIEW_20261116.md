# F-P3 队友交付复核（2026-11-16）

本记录接续 `F_P3_04_FRONTEND_72H_REVIEW_20261113.md` 的 A1–A4、B1–B2、F1 清单。两包均作为本地交付证据读取；没有将其源码覆盖当前 `codex/landing-sage-ui`，也没有把离线结果当作正式 API 回执。

## 包身份与完整性

| 交付 | ZIP SHA-256 | 核对结果 |
| --- | --- | --- |
| `OpenGuard_xzb__后端A交付包(2).zip` | `b545b57076323052d0b27ac1b2d1712b1f61eeb881665d79e5b3f826d21bd68c` | 包内 `FILE_HASHES.json` 列出 1,782 个文件；逐个解压流复算字节数和 SHA-256，1,782/1,782 匹配，0 缺失/漂移。包本身是 2026-11-14 的 Gemini UI + portable 后端新组合，交付者明确标为内部交接、未冻结验收。 |
| `OpenGuard-B-P4-Frontend-20261115(1).zip` | `5d4d5d280fb2548a534cf1eb79767f0cb4295855493ed497a92f60730df682c6` | 四个内容文件与 `SHA256SUMS.txt` 全部匹配；包含开发重放 JSON、错版拒绝样例和说明。正式同版业务联验标为未运行。 |

## 对 P3 缺项的结论

| 原清单 | 本轮已获得 | 仍需关闭的门禁 |
| --- | --- | --- |
| F-P3-01 / A1 候选身份 | A 包有独立组合身份、逐文件哈希、源码、锁文件和候选说明。当前本地 UI 分支与 A 包 Gemini 源码是不同候选，不合并认定。 | 队长选定**唯一**国赛组合，给出该组合 manifest、当前前端与后端/Schema 对应身份；A 包现有 `web/` 未证明由包内最新源码重建。 |
| F-P3-02 / A2–A3 页面与 DTO | A 包提供旧 P2 v1 Schema、API、DTO、上传/CAS/历史合同索引；TASK35 的 `/3 material-claims` 仅在独立参考树。B 包给出离线 `result.subject/scope/distribution`、`link` 和 `gap` 正反例。 | 确认首期 PurposeAdvice 和 ClaimLink 正式 DTO、错误码、版本绑定及材料各阶段 HTTP 回执；不能直接按 B 私有适配器字段接正式页面。 |
| F-P3-03 / B1–B2 操作与证据 | B 包给出固定 `openguard:first-party@2cc7f63` 的 LICENSE/README 字节区间与 SHA-256；§4(a) 条件、§4(b) 合成用途、缺事实、错版本四种离线结果。错版结果为 `review_required`、`subject_binding_mismatch`、`link=null`。 | A 需提供获准环境中的保存、解析、绑定、采用、重研判和拒绝回执；材料负责人复核条件、真实用途和原件权限。当前独立项目数为 0，不能据开发样例宣称精确率或闭环。 |
| F-P3-04 / A4、F1 三方签认 | A 的 A1–F1 状态表与 B 的前端回填格式均已收到；本地 UI 按钮升级后 `pnpm test` 187/187、`pnpm build` 通过。 | 队长确认候选和隔离数据根、端口/预算/写入范围；前端在该候选上重建并做真实同版路径；A/材料/前端/Sol 分别签接口、语义、浏览器与报告快照。 |

## 本地可执行的下一步

收到唯一候选 manifest 与正式 DTO 后，先复算前端与后端/Schema 身份，再按同一 `scan_id → assessment_id → version → result_id` 记录真实请求、DOM/URL 和截图。正例要求定位原件与规则版本；缺事实保持待补；错版本以拒绝为终点；最后导出指定旧/新快照报告并核对固定版本。当前两包足以补足 P3 的**交付盘点与离线正反例设计**，不足以宣称 P3 正式同版联调或三方签认完成。
