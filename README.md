# OpenGuard · AIC AI+开源国赛 P3–P7 候选

OpenGuard 帮助开发团队从本机项目中发现开源资源，将用途、许可材料、证据和风险关联起来，并导出可按版本复核的评估包。候选版本为 `aic-national-p3-p7-20261122-candidate`，等待 Owner 接纳。国赛 Release 和远程 tag 尚未创建。文件身份见 `FILE_HASHES.json`，提交链见 `VERSION.json`，验证范围见 `VALIDATION.md`。

## 研判能力

- **用途与原文材料**。v4 按商业使用、分发和修改等已声明用途计算五态主张。完整 MIT 或受支持的 Apache-2.0 原文需匹配精确资源版本与固定来源，才能生成附条件的文本支持。Apache-2.0 展示 §4(a)–(c) 相关条件，若有 NOTICE 则按 §4(d) 保留人工核对。精确匹配 NOTICE 后状态仍为 `UNKNOWN`。
- **依赖与资源角色**。B58 离线识别支持范围内的清单、锁文件及依赖来源，包括 npm/pnpm/Yarn 等已覆盖输入，并保留声明、推断及冲突证据。角色与路径提示不自动删除实际使用资源。
- **增量研判与版本固定**。`A-P4-04` 在补充材料或回答后输出影响集、重算和保留资源及主张，固定旧版本和使用过的依据。P5 工作台呈现研判概览与「上传、解析、绑定、采用、触发增量」五段材料状态。当前与历史 Result 各自保留，历史版本只读。
- **审查与导出**。正式 Assessment 与材料 Result 分别保存。报告归档、预览及完整评估包可绑定指定 Assessment 和 Result，并使用摘要核对归档原字节。P6 基准评测与安全回归的执行条件及实际分母见 `VALIDATION.md`。

## 安装和本机运行

解压到新的用户可写目录，进入含 `openguard.py` 的 `OpenGuard/`。需要 CPython 3.12（含 venv/pip）、Git 和现代浏览器。目标为 macOS/Linux，Windows 使用 WSL2 Linux 用户目录。已验收的平台和操作仅以 `VALIDATION.md` 为准。

```sh
python3.12 verify_package.py
python3.12 openguard.py setup
python3.12 openguard.py check
python3.12 openguard.py start
```

`setup` 在本包 `runtime/venv` 准备 `deployment/requirements.lock` 的 27 项固定依赖，默认需要访问 PyPI。包内未附 wheelhouse。已有适配当前平台及 CPython 3.12 的完整离线 wheelhouse 时，将 setup 命令替换为 `python3.12 openguard.py setup --offline-wheelhouse /path/to/wheelhouse`。若已有满足同一锁文件的 Python 3.12 venv，可用其解释器直接执行 `openguard.py check`。P7 解压检查使用既有环境，不进行首次安装验收。

打开终端显示的本机 `READY http://127.0.0.1:端口/`，在新的 TEST_ONLY 运行目录自行注册。可用 `--port` 指定空闲端口。按 Ctrl+C 结束本次服务。预构建页面在 `web/`，运行时无需 Vite 或 Node。账号、会话、扫描和报告写入新包的私有 `runtime/`，应与旧目录分开。

## 固定演示路径

1. 新建扫描并上传 `samples/is-number-7.0.0-derived.zip`。它是上游 npm 包派生的四文件 ZIP，4172 字节，SHA-256 `a70563664327b7dc5ad8ee99136c508534e2cef3aeb690beb13b13ed710bca06`。
2. 选择商业使用、分发和修改三项演示用途。用途记录是操作人输入，给审查结论提供上下文。
3. 打开项目评估并查看 v4 初判概览，定位 `is-number@7.0.0`。补充 `samples/is-number-LICENSE.txt`，选择准确版本与来源，保留材料待复核边界。
4. 对比 r1 和 r2 的状态与影响集。上一版通过其原 ID 读取，新的材料与影响范围留在新版本。
5. 保存 Assessment 报告并预览归档，再导出当前 Result 的完整评估包。复核导出中的版本绑定与 SHA-256。评估导出包用于审查，应上传原始项目 ZIP 执行扫描。

`samples/http-server.bundle` 是启动器同时校验的固定兼容样例。其精确上游来源和本轮批准登记的内层测试夹具见 `RESOURCE_USAGE.md`。Apache 实验对照夹具与 P5/P6 测试运行数据单独保存在验收证据目录。

## 可选本地模型

固定身份为 Ollama `0.33.3`、`qwen3:4b-instruct-2507-q4_K_M`，模型 manifest digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。本包不含权重或模型服务。已在本机单独准备模型时，可运行 `python3.12 openguard.py model-check` 检查版本与标签。历史恢复结果及本轮零模型调用范围见 `VALIDATION.md`。

确认模型身份后，用户可在评估 AI 或项目智询中明确发起分析。模型结果辅助阅读，并与正式 Result 分开存储。扫描、材料、版本比较和导出可独立运行。网络来源自动获取、外部扫描器和自动 Qwen 在交付启动配置中关闭。

## 使用边界

- 发现证据、材料完整度、文本支持、条款适用和实际履约分开展示。带条件的 `SUPPORT` 需要按实际交付核对，`UNKNOWN` 或 `pending` 表示证据不足或待审。
- 409 时重新读取当前 Result 并重新核对操作；保留固定历史版本，避免自动重放旧请求。
- 文件或固定依赖校验失败时先核对 ZIP、包内清单与版本。范围外材料和不支持的许可证保留原证据及待审状态。
- 本候选用于可信本机 TEST_ONLY 演示与复核。单平台结果、有限样本和模型历史记录各有独立验证边界。产品及第三方使用范围见 `LICENSE`、`RESOURCE_USAGE.md`。
