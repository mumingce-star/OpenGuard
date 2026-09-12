# Cross-owner change requests

## CR-20260905-B1-B7-closure

- Requested by: CZ, 2026-09-05.
- Scope: continue B1–B7 implementation using the frozen P0 domain contract.
- Target files: `backend/app/scanners/`, `backend/app/licenses/`, `backend/app/detectors/`, `benchmarks/`, and their unit fixtures/tests.
- Ownership impact: backend implementation is normally Terra-owned and test/bench content Luna-owned. The user explicitly authorized direct completion in this conversation.
- Contract impact: additive modules only. `Resource`/`Evidence`/`RiskFinding` P0 schema, source-evidence gate, and no-legal-advice semantics remain unchanged.
- Verification: deterministic fixture tests, schema-compatible model construction, `compileall`, and targeted pytest. Linux-only external-tool ZIP gates remain separately reported if the host cannot evidence them.

## CR-20260913-java-backend-migration

- Requested by: 用户，2026-09-13。
- Scope: 审计 `backend/app/**/*.py`，以 Java 作为新的后端运行时主线；优先迁移领域模型、受限仓库扫描、依赖/许可证/AI 资源发现、规则结果和结构化报告。
- Target files: 新增 `backend/java/` Maven/Spring Boot 模块及其测试、迁移规范、协调记录；既有 Python 文件在 Java 契约与安全回归通过前作为兼容基线保留，不删除、不覆盖。
- Ownership impact: `backend/` 通常由 Terra 负责；本次由用户明确授权 Root 直接实施。变更将触及不可信路径、Git 输入和外部工具边界，必须保留不执行目标代码、不安装目标依赖、证据优先与人工复核语义。
- Contract impact: 保持 P0 JSON Schema、`unknown`/`review_required` 语义和报告证据链；Java 输出新增而非替换已发布 Python API，生产切换需另行验收。
- Verification: Maven 单元测试、固定样例契约校验、真实受信任检出仓库扫描、JSON/CSV/HTML 结构化产物校验，以及 Python/Java 对照测试；外部 ScanCode/Syft 仅在其可执行文件已固定并可用时启用。
