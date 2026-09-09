# 前后端连接与异机运行核查（2026-09-09）

## 结论与版本范围

本轮业务基线为本地 `codex/scan-reliability-integration@d2ffe4c`。该版本前后端没有完成真实连接：可以构建和访问演示前端，但没有 HTTP API 服务入口。

刷新 GitHub 后，团队 `origin/integration/p0@5ad0073` 已有真实 API、前端服务层和 Compose。它与当前本地分支是不同版本，不能将它的能力算作本地版本已完成。团队指定 Windows 共同验收源码为 `b86658e37286f132bf098f0e7642bf25e557ffa9`；从该提交到 `5ad0073` 仅四份说明/协作文档变化，业务代码未变。

异机结论：**尚未完成实测，不能判为通过**。本机未发现标准安装路径的 Docker Desktop CLI，当前环境也没有可用 docker 命令；WSL 返回尚未安装提示。没有获得第二台机器或部署地址的可执行访问条件。本轮没有安装/启用系统组件，也没有改变产品源码或合并分支。

## 实际执行结果

| 检查 | 结果 | 可证明的范围 |
|---|---|---|
| 用户环境版本 | Node 26.2.0、pnpm 10.30.0、Python 3.12.10 | 本机工具可执行，不代表 Linux 工具链已具备 |
| 当前前端锁文件安装 | `pnpm.cmd install --frozen-lockfile --ignore-scripts` 通过 | 未改锁文件；依赖留在已忽略的 node_modules |
| 当前前端生产构建 | `pnpm.cmd run build` 通过，Vite 8.2.2 | TypeScript 与生产包构建可用 |
| 当前前端 HTTP 深链接 | 临时 preview 的 `/app/new-scan` 返回 200、text/html | 静态前端可访问 |
| 当前前端 API 路径探针 | `/api/v1/scans/probe-read-only` 返回 200、text/html、HTML 文档 | Vite 回退到 SPA，而非后端 JSON 响应；HTTP 200 不能当作 API 接通 |
| 后端五组定向回归 | 67 passed，1.86 秒 | P0 模型、外部适配、B4/B6/B7、B5、实际 Bench 输出的局部逻辑 |
| ZIP 平台探针 | 1 failed、1 passed、17 deselected | 正常 ZIP 在 Windows 因平台安全能力失败；拒绝非 POSIX 的测试通过 |
| 最新团队集成代码 | 静态接线存在 | 本轮没有运行该分支的容器或浏览器端到端测试 |
| 第二机器部署/访问 | 未执行 | 没有第二环境回执；也未建立本机 Docker 基线 |

后端定向命令（项目根目录，PowerShell）：

```powershell
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_p0_domain_models.py tests/unit/test_b2_b3_external_tools.py tests/unit/test_b4_b6_b7_extensions.py tests/unit/test_b5_license_rule_engine.py tests/unit/test_benchmark_actual_static_assets.py
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_a2_zip_ingestion.py -k 'valid_zip_has_stable_inventory_digest_and_is_cleaned or non_posix_startup_fails_closed'
```

正常 ZIP 原始异常：`scanner_failed:posix_security_capability_unavailable`，触发点为 `backend/app/security/secure_dir.py:46`。这是使用 dirfd/no-follow 安全边界的环境要求，不应通过移除校验来使 Windows 用例变绿。一次补充 `python -c` 探针因 PowerShell/native 参数引号处理失败，未作为项目失败证据；随后以上既有测试取得了真实平台异常。临时前端 preview 已在 finally 中停止，本轮未遗留服务。

## 原因与处理方案

### 1. 当前本地前端是演示版

`frontend/src/App.tsx:5` 引入 `mocks/data`；130 行显示 MOCK MODE；191 行的开始扫描仅跳转页面，未提交 URL 或 ZIP；202 行通过每 1400ms 的定时器推进模拟进度。ZIP 选择按钮没有真实文件输入处理。`frontend/vite.config.ts` 无 API 代理。修改环境变量或仅启动页面不能补齐这些功能。

处理：以团队已指定的 `integration/p0@b86658e` 在独立目录验收，核对已实现的服务层；若要把该版本整合进当前开发分支，再按独立的合并任务审查 B4–B7 差异并回归。当前分支名称带 integration 不等于包含最新集成实现。

### 2. 当前本地缺少 HTTP 后端及部署文件

当前 `backend/app` 没有 `api` 模块或 FastAPI 路由，`backend/pyproject.toml` 没有 FastAPI/uvicorn 运行依赖；`deploy` 只有说明，没有 Compose。CLI 和解析器通过单测无法证明 HTTP 接口存在。

团队集成版本的对应链路如下（均来自 `5ad0073` 的静态审查）：

| 环节 | 代码与配置 |
|---|---|
| 默认真实模式 | `frontend/src/services/scans.ts`，默认 api，base 为 `/api/v1` |
| 创建任务 | `createApiScan`，ZIP FormData / Git JSON POST `/scans`，携带 idempotency_key |
| 状态与结果 | `useScan.ts` 对 queued/running 每 2500ms 轮询；services 读取 resources、risks、evidence、report |
| 后端路由 | `backend/app/api/main.py` 的 `/api/v1` router，包括 POST scans 与状态/资源/风险/证据/报告 GET |
| 开发代理 | Vite 的 `/api` 转发到 `127.0.0.1:8000`，dev/preview 均配置 |
| 容器代理 | nginx `/api/` 转发到 `api:8000`，保留请求 URI |
| 部署 | Compose 提供 web/api，API 使用扫描工具镜像、持久 data 卷与健康检查 |

因此集成版本在代码层已接线；完整部署是否可用仍须实际 HTTP/浏览器/容器运行验收。本次没有用 Mock 请求测试冒充真实 API。

### 3. Windows 原生运行不满足 ZIP 扫描安全条件

`SecureRoot.open` 显式要求 POSIX，并探测 O_NOFOLLOW、O_DIRECTORY、dirfd 操作等能力。当前 Windows 正常 ZIP 用例在初始化就被拒绝。Python/pnpm 安装成功并不能提供这些 Linux 能力。

处理：完成 WSL 2 与 Docker Desktop 的 Linux containers 环境，确保 `docker version` 同时有 Client/Server，`docker compose version` 可运行。集成版本还使用 Landlock/seccomp，须运行真实工具 smoke，不能仅凭镜像构建或容器 healthy 宣称扫描通过；不支持安全能力时保持失败关闭。

### 4. “异机部署”和“另一台电脑访问本机”不同

团队 Compose 发布地址为 `127.0.0.1:${OPENGUARD_WEB_PORT:-8080}:8080`，本地前端 dev/preview 也绑定回环。因此在另一台机器输入本机局域网 IP 无法访问属于当前配置行为；输入 localhost 则会访问另一台机器自己。

独立部署应在每台电脑各自构建/运行，然后访问各自 localhost。若目标是局域网共享服务，需另外确定可信网卡、访问控制、防火墙和代理方案，不能将无鉴权 API 直接暴露公网作为“修复”。本轮未改绑定或防火墙。

## 可复现的后续异机验收

使用团队现有[Windows 共同验收说明](https://github.com/mumingce-star/OpenGuard/blob/5ad0073/deploy/README.md)，源码固定 `b86658e37286f132bf098f0e7642bf25e557ffa9`。在新的空目录准备副本，保留原开发工作区。Docker/WSL 就绪后，在该副本依次执行：

```powershell
$env:OPENGUARD_ENABLE_PUBLIC_GIT = '1'
$env:OPENGUARD_ENABLE_AI = '0'
$env:OPENGUARD_OLLAMA_DOCKER_HOST = '0'
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml up -d --build --wait
docker compose -f deploy/compose.yaml ps
$acceptanceOutput = Join-Path $env:TEMP ('openguard-acceptance-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
py -3 deploy/smoke.py --external-scanners --ai-assets --wait-seconds 900 --output $acceptanceOutput
```

每步失败应停止并留存结果。随后按原说明验证 sampleproject Git（记录实际 revision）、固定 smolagents ZIP（验证 SHA）、四格式报告、实际浏览器保存、无在途任务时容器重建后的原报告 SHA，以及失败后任务/进程状态。两台 Windows 都执行无 AI；至少一台追加团队锁定 Qwen 的真实测试。无 AI 观察上限 900 秒，Qwen 1200 秒，这是样例验收上限，不是全链硬 deadline 或性能目标。

回执至少含源码 SHA、系统/架构、Docker/Compose 版本、容器健康状态、任务 ID/终态、工具版本与证据 SHA、报告 SHA、脚本退出码、等待/失败记录、浏览器保存结果。原始材料放本机输出目录，公开记录去除绝对路径、凭据及个人信息。旧 Mac 记录与静态审查不替代新 Windows 实测。

## 当前未关闭门禁

- 当前开发分支：真实 API/前端/部署尚未整合，由 Root/主线实现负责。
- 本机环境：Docker/WSL 未就绪；需要设备操作者完成管理员步骤和必要重启。
- 异机：第二台机器的访问条件或执行回执未提供；两台 Windows 验收仍待实测。
- 竞赛：报名/权属由负责人确认；完整作品仍需端到端、异机、安全和材料验收；竞争力仍需独立标注、基线/消融与用户证据。本轮没有重新审计这些门禁，不给完成百分比。
