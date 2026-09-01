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
