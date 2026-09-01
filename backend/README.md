# Backend 模块

计划包结构：

```text
app/
├── api/             # scan、findings、reports、benchmarks
├── ingestion/       # repo、zip、workspace
├── scanners/        # scancode、syft、manifest、AI assets
├── domain/          # 统一数据模型
├── knowledge/       # SPDX、OSI、许可证义务
├── risk/            # 确定性规则和证据链
├── ai/              # 结构化抽取、解释和整改建议
├── reports/         # HTML、JSON、CSV、资源清单
├── persistence/     # SQLite 与迁移接口
└── security/        # 限额、路径、防泄漏和清理
```

第一阶段不执行目标仓库代码，也不安装其依赖。
