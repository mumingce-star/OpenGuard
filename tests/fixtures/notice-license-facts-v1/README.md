# NOTICE 与许可证关系事实包 v1

本目录是 Report V2 的**事实与草稿数据输入**，不是最终报告快照、下载 API、许可证法律意见或分发许可清单。

`facts.json` 统一表达根项目、依赖和 AI 资源的 LICENSE、NOTICE 与 copyright 观察；每条来源携带稳定 locator、SHA-256、短摘录和验证级别。`report_v2_rows` 已按报告附件七组字段整理，可被 Report V2 读取，但所有行保持“待核验”。`schema.json` 是本事实包内部的版本化草稿契约，不修改公共 P0/P1 Domain 或 API。

真实演示来源包括：根目录 `LICENSE`；固定 Maven artifacts 中 Jackson Databind 与 Spring Boot 的 Apache LICENSE/NOTICE；Hamcrest 的 BSD-3-Clause LICENSE/copyright；Mockito 的 MIT LICENSE/copyright；以及已发布 Hugging Face 固定元数据快照中的原始 license 声明。

gap 是事实，不会被空值吞掉：根 NOTICE/copyright 来源缺失、依赖未打包独立 NOTICE、AI 资源未观察到 NOTICE/copyright/许可证原文，以及 `other` 无法解析均使用稳定 gap code。`license_expression_id` 全部为 `null`，后续规则与人工审核可在独立证据链上决定是否产生正式表达式。
