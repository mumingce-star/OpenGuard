# 本机 Git 扫描运行修复回执 · 2026-10-24

## 结论与范围

本机日常入口 `http://127.0.0.1:4189/app/new-scan?mode=api` 已连接启用公开 Git 的独立运行实例。真实浏览器提交、完成、结果页、下载及重启读取通过；本轮没有修改后端业务代码、前端产品代码、Schema 或依赖，没有 Git 提交、推送、合并或生产部署。

原错误是旧 API 的 `OPENGUARD_ENABLE_PUBLIC_GIT=0`，不是前端按钮故障。原容器依赖的旧镜像对象已经不存在，同名标签已漂移，故没有直接重建旧 Compose。保存原容器文件系统为本机快照后，使用原数据的独立校验副本运行。此快照不是团队正式发布镜像，不据其标签伪造源码提交身份。

## 实际身份与保护措施

- 新容器：`openguard-git-runtime-20261024`，仅回环端口 `15178:8000`；4189 预览通过现有环境变量代理到此端口。
- 本机镜像：`sha256:1281101c2a94434742af5e44831e8f94ba5df965cf2cf9f48fd5d4e897f2f7c7`，linux/amd64。
- 原运行容器与新容器的 115 项 backend/rules/schemas 文件逐项 Hash 一致；清单摘要 `6b43fe57d01a477e565243f024ccdba5784c0bed25d4e5316238209d88374b52`。源码 Git SHA 未冒认；前端仍是 `codex/uiverse-ui-upgrade@2ee6003877e38a248b46fb21fc7cbcd7d5931eea` 加既有未提交精修。
- 12 条原历史、78 个数据文件在无活动任务时离线备份，并复制至 D 盘承载的既有 WSL 中全新私有根；逐文件校验通过。原容器随后立即恢复，8082 与原卷保留。
- Git=1、AI=0，保留 UID/GID 10001、私有目录 0700／文件 0600、只读根、cap_drop ALL、no-new-privileges、原内存/进程/CPU限额和 TrustedEgress。没有 chmod 777、关闭校验、外部模型调用、init/apply 或合并数据集。
- 18011 合成规模、18117 固定真实 Obligation、15177 P2 开发空间均未用于创建本次扫描，原服务保持运行。

## 三次明确提交的真实结果

| 输入/任务 | 结果 | 解释 |
|---|---|---|
| xzb123-hash/OpenGuard / `scn_07e6266c-3fda-42f0-b4f2-5115372e992e` | 202 后 failed，`dependency_manifest_not_found` | 实际 revision `476d954998be6ed943532791530f5d6234f4893f`；没有伪造资源，保留失败及技术诊断。这里只能说明该镜像没有识别出依赖清单，不能据此断言仓库没有任何依赖。 |
| openai/openai-quickstart-node / `scn_befc6555-f86e-4e15-ba8f-c8eb77aafed7` | 202 后 failed，`invalid_source` | 一次获取失败；安全获取器随后只读诊断成功。没有绕过校验，原失败保留。 |
| 同一公开仓库受控重试 / `scn_678ef67a-3585-49eb-84a3-f1d26cc62882` | completed，100%，errors=[] | revision `6e6e03496440913a82ccba6f17c2f41caa948c58`；24 components、1 AI asset、40 Evidence、25 review_required Finding。不是合规通过，AI asset 识别不等于调用模型。 |

成功任务的已保存 Formal Assessment：`asm_04779468-6c67-5bdd-af5f-848763827ac4`。所有创建均由真实页面一次 POST 受理，明确失败后才人为选择受控重试，没有自动换 key 制造重复结果。

## 本轮执行的验证

最终只读浏览器 **7 组 PASS**：History 行打开准确 scan_id、资源与 Evidence、Finding、已有 Formal、原报告双格式实际下载、打印正文及390px、用户仓库失败展示、GET-only/数据库校验。实际审计 48 次 API GET，0 非 GET、0 意外错误/pageerror；5 项数据库/WAL Hash 前后不变。

明确单列 1 次旧运行镜像不支持的 P2 binding GET：精确对应本成功 Scan/Assessment，404/`invalid_source`/`route_not_found`。没有算作 P2 成功；P2 继续使用原独立入口4184，不因本次 Git 运行修复升级整个后台。

新成功任务下载与重启后 Hash 一致：

- JSON（93,778 bytes）：`4105fcc563143ffd5520901bb156a37ff9c059318958d3d743ed675d0be3476c`
- HTML（55,246 bytes）：`aa4e92f67bd68bc45f9d24de8c17ad5b83c241e2492891b8fea0aaa75e795a12`

仅重启新实例后，15 条副本历史的 ID、状态、revision、summary、Assessment 引用不变，原8082仍12条；再次执行同一只读浏览器7组通过。原历史样本 `scn_76ba88fa-d8fd-4595-be83-419ee0d579b5` 的 JSON/HTML 与原服务逐字节一致。报告页需展开“查看历史扫描报告、四种原始附件与全部明细”查看 P0 原件。

证据留在本机忽略目录 `output/git-runtime-20261024/`：backup-hashes、runtime-identity、preservation、restart-receipt、三次创建响应、独立终态、最终 `browser-after-restart/receipt.json`、实际下载与截图。初次浏览器定位失败保留于 browser-1 至 browser-4，分别是 History 不显示完整 scan_id、Assessment ID 位于 select value、原报告折叠、失败详情折叠；均只改测试定位，没有改产品或降低业务断言。browser-5 为重启前最终通过，browser-after-restart 为重启后通过。

前端冻结16文件Hash无变化；沿用先前148项/TypeScript/Vite结果，本轮**没有重跑**这些代码检查。`git diff --check` 通过；没有把7组重复执行相加为14个唯一场景。

## 尚存边界与责任

- 截图中的个人 OpenGuard 仓库输入仍有清单识别失败；需按其实际材料核对既有解析器支持范围或选择包含受支持清单的项目。前端不补造依赖。
- GitHub/网络偶发获取失败仍可能发生，保留真实原因，不承诺任意公开仓库均完成。
- 新实例为原日常镜像的本机快照，不代替后端正式 P2 镜像/生产 NOTICE、人审、旧报告和评测等原门禁；仍由 Owner 及原责任方复核。
- UI 视觉最终签收与 Git 上传仍待 xzb 明确授权。本次没有增加新视觉功能。

本次运行精确 token 数不可获得。开工估算5,000—12,000；发现旧镜像对象缺失后增加本机快照和独立副本验证，实际消耗是否落在估算内无法核定。运行修复授权范围已完成，不宣布整体作品100%。
