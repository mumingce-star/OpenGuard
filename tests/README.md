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

## A3-1 FastAPI API 复现

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a3_fastapi_api.py
```

测试使用临时私有 SQLite 注册表和 FastAPI TestClient，不访问网络、不克隆 Git 仓库、
不运行扫描器。它覆盖六条 OpenAPI 路径、Git JSON 创建、持久化与幂等、queued 状态、
资源/风险/证据/报告读取与过滤、统一脱敏错误，以及默认数据目录权限。为验证读取投影，
测试会把仓库内合成 P0 sample 通过 A3-0 的合法状态迁移写入临时注册表；这不是产品运行时
伪造的扫描结果。

## A6-0 报告导出核心复现

```bash
PYTHONPATH=backend python -m pytest -q tests/unit/test_a6_report_exports.py
```

该测试覆盖稳定 JSON、七字段 CSV/资源清单、HTML 转义与 CSP、CSV 公式注入防护、
`partial/rules/70` 的诚实披露、非终态拒绝和输入对象不变。它不证明报告已接入 Pipeline、
持久化、HTTP 下载或前端，也不替代 B5 许可证规则。

## A6-1 报告持久化与下载复现

```bash
PYTHONPATH=backend python -m pytest -q \
  tests/unit/test_a6_report_exports.py \
  tests/unit/test_a6_report_delivery.py \
  tests/unit/test_a3_fastapi_api.py
```

新增测试覆盖私有目录/文件权限、内容寻址与 metadata 原子提交、幂等、重启读取、长度/摘要、
篡改/缺失/symlink 失败关闭、默认数据目录、P0 `ReportLink`、FastAPI 元数据和只读下载、安全响应头、
稳定脱敏错误及方法边界。下载前后文件时间必须不变，证明 GET 不写入。测试用终态快照由固定 sample
和内存构造的 `partial/rules/70` 产生；不会实现或伪造 B5，也不代表 Pipeline/前端已经接线。
