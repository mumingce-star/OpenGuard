# P2 本机隔离运行回执（2026-10-15）

状态：**开发联调 PASS；锁定镜像正式接收仍 PARTIAL**。

## 原因定位

- Docker Engine 已恢复，版本为 `29.7.2 linux/amd64`。
- `8082` 中断不是前端代码或数据库损坏：对应旧 P1 Compose 容器配置为 `restart=no`，Docker Engine 重启后容器未自动恢复。原 API/Web 容器已原地启动，未重建或迁移数据，`http://127.0.0.1:8082/` 返回 200。
- P2 统一 TEST_ONLY 包存在且 SHA256 为 `743600b7748d07df7dcb587617cfc3825547d58e53cad33eb95c348905275854`。
- 正式接收说明锁定镜像为 `sha256:6510aeaf29bdcfb1b3bdb3655fef73d39f9bc6164ae876011a57c356c5cef23c`；本机无该镜像，包内明确未包含镜像。因此不能把本轮开发实例标为锁定环境正式签收。

## 本轮隔离实例

- 候选源码：交接包 `SOURCE.zip`，候选 `ec4c680bf7bb0d7d0af583e5376336421361fc8d`。
- 数据等级：`TEST_ONLY`，不代表生产历史、真实项目许可适用性或人工签认。
- 数据根：专用 WSL `OpenGuard-Receiver-Ubuntu` 中 `/opt/openguard-p2-dev-20261015`；该 WSL 发行版存放于 D 盘项目 `output/receiver-runtime/wsl`。
- 恢复：使用包内 `restore_data.py`，输出 `RESTORED_TEST_ONLY`；没有执行 init/apply，没有覆盖既有 P1 或真实 Obligation 数据。
- 开发替代运行镜像：`sha256:6514fdf0abee6925b3c00671a20ddfdf65e09c3ac8acc666153d69556005d6f1`。它只提供匹配的本机 Python 运行时，**不等于**锁定镜像 `6510aeaf...`。
- 容器：`openguard-p2-dev-receiver-20261015`，只发布回环地址 `127.0.0.1:15176`；AI、公开 Git、Profile Metadata、外部扫描器和 Durable ZIP 均关闭，P2 为只读 TEST_ONLY。
- 当前前端预览：`http://127.0.0.1:4183/`，代理到 `http://127.0.0.1:15176`；没有修改 Vite 配置。

## 验证结果

- API OpenAPI：`GET http://127.0.0.1:15176/openapi.json` → 200，114,776 bytes。
- 交接工具精确 GET：首次 27/27 PASS；停止/启动自有容器后再次 27/27 PASS。
- 两次 GET 回执文件 SHA256 均为 `893e93d2ea96352600410ff16eb419b87d29277d644f8c69f72f157a0a2cd54a`。
- 当前 7 个 SQLite 数据库的规范化表状态与交接包最终基线完全一致；两轮 GET、容器重启和浏览器刷新没有数据库写入副作用。
- 浏览器真实 API 页已打开并刷新恢复：固定 Assessment v1、P2 Result revision 3、TEST_ONLY 提示、`pending/待核验`、Evidence、Material ref、非 Formal Summary 和只读写入禁用均可见。
- 旧 P1：`8081` 返回 200；`8082` 原容器恢复后返回 200。没有重建、更新镜像或迁移旧数据。
- `git diff --check` PASS；本轮没有产品代码、后端业务、公共 Schema、依赖、提交、推送、合并或部署变更。

## 可用地址

- P1 既有环境：`http://127.0.0.1:8081/`
- P1 新版既有环境（已恢复）：`http://127.0.0.1:8082/`
- P2 隔离开发 API：`http://127.0.0.1:15176/openapi.json`
- P2 当前前端预览：`http://127.0.0.1:4183/`
- 固定 P2 页面：`http://127.0.0.1:4183/app/scans/scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d/assessment?mode=api&assessment_id=asm_6c664ed7-7c41-512c-bbcc-a178a8edea79&assessment_version=1&p2_result_id=p2res_eabfaa020c8a91cd4a5a309861ad4f0ab90cae07263d4ac48370b8a02b89fc83&p2_revision=3`

## 尚不能代替的正式门禁

只剩运行环境身份这一项无法由现有材料自行补造：需要 Owner 提供上述精确 `linux/amd64` 镜像的可信离线 tar 与 SHA256，或书面冻结另一完整镜像 ID 作为新的正式接收基线。收到后可以复用本轮全新数据根流程重做正式签收；cz 无需重复交付既有 P2B 源码或 TEST_ONLY 样例。
