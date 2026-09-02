# 测试策略

- 单元测试：解析器、标准化、规则和报告；
- 集成测试：ScanCode/Syft 到统一模型；
- 端到端测试：提交仓库到导出报告；
- 回归测试：固定基准集；
- 安全测试：路径穿越、压缩炸弹、超时、超大文件和密钥脱敏；
- AI 测试：JSON Schema、证据引用、幻觉和不确定性处理。

## A1 领域契约复现

在项目根目录执行以下命令，验证 Pydantic 模型、Draft 2020-12 Schema、sample
和公开边界 fixture：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_p0_domain_models.py
```

运行前请在项目隔离环境中安装 `backend/pyproject.toml` 的 `dev` 依赖；不要把本机临时环境路径写入公开复现说明。

测试覆盖跨对象引用类型、partial/error、locator 路径边界、错误信息脱敏、AI
候选 pending、summary 四态、终态时间、未知字段和公开 fixture 去敏检查。该命令
不会执行被扫描项目代码或安装其依赖。

## A2-0/A2-1 本地 ZIP 安全复现

在项目根目录执行：

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a2_zip_ingestion.py
```

该实现侧测试只动态创建小型 ZIP 字节流，不保留二进制 fixture；覆盖 POSIX 启动失败
关闭、稳定 inventory/root digest、成功与失败清理、路径穿越/Windows/home shorthand 路径、重复与
Unicode 碰撞、文件目录冲突、链接属性、加密、CRC 损坏、central/local header 尺寸
不一致、条目数、单文件和压缩比限制；同时断言冻结的 `details.reason` 枚举（包括路径
深度与 UTF-8 长度配额）。
它不替代 Luna 需要补充的真实 TOCTOU、ZIP64/多卷/异常 header 语料、边界矩阵、Linux
sandbox 和 TrustedEgress 集成证据。

## A2 本地 ZIP CLI 演示复现

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a2_zip_cli.py
PYTHONPATH=backend python -m app.cli ./demo.zip
```

实现侧测试覆盖成功 JSON 的稳定字段与排序、安全拒绝的 stderr/退出码、参数或文件错误
脱敏，以及成功和失败后的 task workspace 清理。CLI 只演示本地 ZIP→inventory，不替代
Git、依赖/许可证扫描、Web API 或完整 A2 系统门禁。
