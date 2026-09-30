# Detector 0.3 静态资源识别：固定 Bench 证据

本记录只描述离线固定语料 `cases/detector-03-static-assets.json` 的可复现结果，不表示真实仓库总体准确率、实际服务调用、授权、许可证适用性或合规结论。

运行：

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_detector_03_static_assets.py
```

本次固定语料包含 7 个正向标签与 4 个反例：ModelScope 数据集 URL；OpenAI、Anthropic、Google 的 JavaScript/TypeScript 已导入且已构造 SDK；三种显式环境配置键；普通 URL、动态字符串、无关环境配置与仅出现 SDK 名称的文本。测试输出 `TP=7`、`FP=0`、`FN=0`，micro Precision、Recall、F1 均为 `1.0`。

每次运行还为每个差异输出以下分类：

- `FN_UNDETECTED_STATIC_REFERENCE`：固定期望标签未被当前版本检测到；
- `FP_UNEXPECTED_STATIC_REFERENCE`：当前版本产生了固定期望之外的标签。

本次分类列表为空。其含义仅是该固定语料未观察到差异，绝不外推为真实项目零漏报或零误报。

Detector 0.3 的统一候选视图为 `StaticAssetCandidate`：`resource_type`、`provider`、`name`、`source_url`、文件 `locator` 与行号、`rule_version=0.3.0`、`evidence_id`、`evidence_sha256`、`review_status=review_required`、`authorization_status=pending`。环境变量值从不进入证据摘要；静态候选不自动生成许可证表达式、义务、风险或授权结论。
