# Java 后端运行时迁移

## 已迁移的可执行纵切

`backend/java/` 是 Maven/Spring Boot Java 25 模块。当前可以在不执行目标项目代码、不安装目标依赖的条件下，对显式受信任的本地检出目录完成：

- Python `pyproject.toml` 与 `requirements*.txt` 的直接依赖发现；
- Node `package.json` 的直接依赖发现；
- 许可证文本候选、SPDX 候选和 `pending` 人工核验状态；
- Hugging Face、Kaggle、ModelScope 静态 URL 的 AI 资源引用发现；
- `review_required` 风险提示，以及 JSON、CSV、HTML 三种结构化报告。

对应命令必须显式给出受信任检出目录：

```powershell
cd backend/java
mvn test
java -cp target/classes;... dev.openguard.scan.RealRepositoryScan --trusted-checkout <目录> <来源标识> <输出目录>
```

CLI 不提供远程 URL 自动检出，也不会调用 ScanCode、Syft、Python、Node、包管理器或目标仓库中的任何代码。

## Python 模块审计与替换状态

| Python 区域 | Java 状态 | 迁移判定 |
| --- | --- | --- |
| `domain/models.py` | 部分 | Java `ScanResult` 已覆盖本次扫描/报告的不可变 DTO；完整 P0 `ScanRun` 图仍需按冻结 Schema 扩展。 |
| `scanners/python_*`、`javascript_*` | 部分 | 已覆盖直接依赖发现；锁文件、PEP 508 完整语义、稳定 UUID 和 P0 mapper 尚未等价。 |
| `scanners/scancode_pipeline.py`、`syft_pipeline.py` | 未迁移 | 需要固定二进制、Linux 隔离与受限子进程适配，不能用简单 Java 进程调用替代。 |
| `licenses/spdx.py`、`rules/engine.py` | 部分 | 许可证候选和人工复核提示已迁移；完整 SPDX AST、规则来源审计和场景三态仍应迁移。 |
| `detectors/static_assets.py` | 部分 | 已覆盖三个公开资源站点 URL；完整静态资源规则未迁移。 |
| `ingestion/*`、`security/*` | 未迁移 | ZIP 防穿越、descriptor-relative 会话与限额属于安全关键路径，保留 Python 基线，需单独 TDD/安全评审。 |
| `cli.py`、API、持久化、AI、pipeline、reporting | 未迁移 | 现有 Java CLI/报告是并行入口；完整 API、SQLite、异步管线和 AI 降级必须以契约测试逐段替换。 |

因此，本模块是 Java 主线的第一条真实扫描纵切，不是生产切换声明。删除 Python 或切换部署入口的前置条件是：完整 P0 Schema 对照、同输入稳定输出对照、外部工具隔离回归、API/数据库迁移和端到端验收全部通过。
