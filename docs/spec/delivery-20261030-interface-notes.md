# F01—F07 本轮兼容性说明

## ZIP 配对差异

既有 GET /api/v1/scans/{target}/diff 增加可选 confirm_zip_pair=false。只有明确true且双方均为ZIP才接受显式配对；非ZIP传true返回400，缺确认仍沿原409身份门槛。同名上传不自动合并；History身份仍scan_only。响应沿ScanDiffView 1.0，project_identity_key=user_asserted_zip_pair:加固定pair摘要，coverage.gaps明确关系未经核验；这种模式不返回确认移除的结论。参数摘要包含选择，差异计算复用原算法和Evidence引用。未改变原扫描/评估。

## 聊天运行记录

ChatStore启动时兼容增加trace_json列，旧行默认空对象；GET不迁移。原turn字段、generation、幂等和正文限制保持，turn新增可选trace，记录模型配置身份/运行版本、提示版本、评估/facts/state摘要、调用尝试数与安全错误标识。旧行无模型记录时显示未记录，不套用当前配置。模型失败不会返回成功回答或更改Formal与原报告。此记录不是独立性能评测或真实模型验收。

## 报告与导航

Report V2保存的HTML渲染器为report-v2-html/1.3，增加固定扫描/输入摘要、资源/覆盖信息并保持原文。下载沿已存字节，旧文件不重渲染，V2不新增CSV。导航保留assessment ID/version、P2结果ID/revision、snapshot ID；换评估清理下游身份，指定旧评估不在首20条时精确读取，不退回latest。

## 权限

普通Compose评估和P2仍默认关闭，只读默认开启。delivery显式评估，P2须EnableP2Write，data_scope为TEST_ONLY。原M1停止点、可信来源门槛和Formal结论保持独立。
