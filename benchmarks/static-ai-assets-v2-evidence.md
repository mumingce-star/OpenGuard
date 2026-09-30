# B02-A 静态 AI 检测器 0.3：固定语料实测与错误分析

本记录是可执行的固定离线语料测量，不是对真实项目总体准确率的主张。语料及期望标签位于 `benchmarks/cases/static-ai-assets-v2.json`，计算逻辑位于 `tests/unit/test_b02a_detector_benchmark.py`；运行时不联网、不执行被测代码，也不会读取或安装被测项目依赖。

2026-09-30 在 Python 3.12 虚拟环境运行该测试，实际输出为：17 个正向资源标签全部命中，`TP=17`、`FP=0`、`FN=0`，micro Precision/Recall/F1 均为 `1.0`。这些数字仅描述该版本化语料：它覆盖 Hugging Face/ModelScope 模型 URL、Hugging Face 数据集 URL、`transformers`/`datasets` 显式字面量调用、OpenAI/Anthropic/Google SDK 构造器以及 JSON/TOML/YAML 中的显式模型、数据集和官方 API endpoint。

错误分析与边界：

- 语料中的普通 URL、Hugging Face 文档路径、动态模型变量及未知 endpoint 都未产生预测，避免把链接、变量或私有代理误写为资源事实。
- 检测器故意不解析 API key、令牌或任意 endpoint；SDK 构造器只证明静态服务引用，不能证明请求成功、实际调用、账户关系、授权或许可证。
- 动态拼接、别名逃逸、反射、非受支持 SDK、非字面量配置和复杂 YAML 都会保守漏报并需要后续扩展或人工复核。因此当前固定语料的零误差不能外推为真实仓库覆盖率，也不能替代独立人工标注、holdout、性能或授权评测。
