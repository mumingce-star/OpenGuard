# UI 精修收尾与真实接口验收回执

日期：2026-10-24。结论：本轮真实接口只读联调 **PASS**；用户最终视觉确认及 Git 上传授权 **PENDING**。未提交、推送、合并或部署。没有新增业务功能。

## 源码和运行身份

- UI 工作线：`codex/uiverse-ui-upgrade`，基点 `2ee6003877e38a248b46fb21fc7cbcd7d5931eea` 加既有未提交精修。该基点不代表本轮未提交代码已上传。
- 本轮产品源码未再修改。16 个前端/测试/来源文件的当前 SHA256 记录在本机 `output/ui-live-closeout-20261024/source-identity.json`，未伪造新 commit SHA。
- Docker Engine 实测 `29.7.2 / linux / amd64`。实际容器镜像、端口和相关功能开关记录在同目录 `runtime-identity.json`。
- P1 规模空间与固定真实 Obligation 空间使用既有镜像 `sha256:8ffe27fbcd8f3e7484df6dd8adc7a53b50eb5e08865b9180cc8c1ff05ad6b7b9`。规模空间源码身份由接收机 manifest 固定为 `aa38f1656aa814075aac12f0e20ac387059530cc`；真实样本交接来源为 `f63a5818b3ef59997ca6d365b75b12099a475079`。
- P2 沿用既有开发实例，镜像 `sha256:6514fdf0abee6925b3c00671a20ddfdf65e09c3ac8acc666153d69556005d6f1`，不是旧交接要求的正式镜像 `6510aeaf…`；本轮不代签正式镜像接收。既有源码交接背景见 `P2_LIVE_WRITE_ACCEPTANCE_20261015.md`。

## 恢复操作

初始 Docker API pipe 不存在，Docker Desktop 未运行。经 Windows 正常 Shell 启动已安装 Docker Desktop 后，Engine 可用；既有容器仍为 exited，符合其停止后未自动恢复的配置。

核对镜像、挂载根和端口后，仅原地启动既有 P1 API/Web、P1 acceptance、固定 Obligation 和 P2 开发容器。专用 WSL 私有数据根保持；没有 init/apply、恢复出厂、chmod、重建/替换镜像或合并数据库。原 4189 预览继续代理 8082；另外三个历史预览端口以同一当前 UI 构建恢复。

| 预览入口 | 后端 | 数据等级与用途 |
|---|---|---|
| <http://127.0.0.1:4189/> | 8082 既有 P1 | 原有本地扫描环境，API/Web healthy |
| <http://127.0.0.1:15174/app/history?limit=100> | 18011 | `real_backend_api + acceptance_synthetic`，用于分页/规模；不是生产历史或真实仓库规模 |
| <http://127.0.0.1:15175/app/scans/scn_6c0f972a-18c1-4566-a7fa-df623053bea5/assessment?mode=api&assessment_id=asm_87baf091-31fe-54f7-88d6-8d3fb788181a> | 18117 | `acceptance_real_reviewed` 固定真实材料；义务履行仍 pending |
| <http://127.0.0.1:4184/app/scans/scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d/assessment?mode=api&assessment_id=asm_6c664ed7-7c41-512c-bbcc-a178a8edea79&assessment_version=1&p2_result_id=p2res_e518330f89aa8a906544867e0543fa30269c498ce40d258bbfa97d2c5fdb5472&p2_revision=6> | 15177 | `TEST_ONLY` 开发 API；独立 Result revision 6，Formal v1 |

三个验收数据空间保持分离。只读验收没有创建扫描、Assessment、Task、Report、材料或模型输出。

## 本轮实际执行

脚本：本机忽略目录中的 `output/ui-live-closeout-20261024/acceptance.mjs`。该脚本访问实际 API；没有业务响应拦截替换。非 GET 业务请求会被测试阻止并判失败。

| 检查 | 实际结果 |
|---|---|
| History 205 条 | API 100/100/5，205 个唯一 ID；浏览器首、中、末页均显示对应条数 |
| Graph 100/300/500 | 实际节点/边分别 **100/283、300/883、500/1483**；键盘选中、详情与刷新 URL 恢复通过 |
| Diff / 资源 | 真实 partial Diff 与覆盖边界可读；真实资源卡片可见；旧固定环境未提供的 Profile 如实显示缺失 |
| 真实 Obligation | `obl_ab81fa16-f42f-5c32-ab20-621ddef958b4`；`LIC-MIT-NOTICE / 1.0.0`；页面待履行/待确认，Evidence 原文可读 |
| 固定 Task | `tsk_a0a72e5b-4772-54e9-91b4-7bfa70d02eb8`，version 1；按 todo 快捷筛选并刷新后仍为同一对象；未 PATCH |
| Report V2 | 固定 `rptv2_5ba69c69-7b03-463c-9ba7-bcaeca1120c4` 原始 HTML 可读；正文锚点未被顶栏遮挡；工具区收起正常 |
| 浏览器下载 | JSON/HTML 实际下载成功，字节 Hash 与交付清单完全一致，见下表 |
| 窄屏/打印 | 390px 页面及打开 Hash 提示无横向溢出；打印媒体正文可见、操作区隐藏。未代签实体打印机或全部分页效果 |
| P2 固定结果 | 实际 GET 读取 revision 6；Formal v1、TEST_ONLY、待核验和非正式结果边界可见；页内导航与刷新恢复通过 |
| 只读性 | 9 次直接 GET + 187 次浏览器 API 响应审计；0 非 GET、0 意外错误、0 pageerror；三空间数据库/WAL 文件 Hash 集合前后完全相同 |

### 实际下载 Hash

| 格式 | Bytes | SHA256 |
|---|---:|---|
| JSON | 320508 | `bb5e0084e39fbb699e0bf724e509cec433f079f6d82a8273c0c564958aec3dcc` |
| HTML | 599543 | `9bd61fbc30d42bb37d6ce7b710380882c3ae3c5024ac26aaed11add494fb20fa` |

浏览器审计中另有 34 次已声明状态：合成扫描 P0 未生成的精确 `409/report_not_ready/not_generated`、旧固定运行时的 Profile 或 P2 binding 404。这些状态保留响应并单列，不被表述成成功数据，也未整体忽略其他错误。P2 成功展示在其独立 4184 实例验证。

## 证据及复用范围

- `output/ui-live-closeout-20261024/run-2/receipt.json`：7 组 live 检查、实际请求路径/状态、下载 Hash。
- 同目录 `databases-before.json` / `databases-after.json`：三个空间完整数据库/WAL Hash 集合；合成规模、固定真实材料、P2 根分别有 4、4、7 个匹配文件。
- 同目录：History 三页、Graph 三档、Diff、资源、真实义务/Evidence/Task、原始报告/打印/手机、P2 截图；下载的 JSON/HTML 原件仅保留在本机忽略目录。
- `run-1/` 初次失败证据保留：测试 `getByLabel('节点详情')` 同时匹配侧栏及关闭按钮；改为精确 complementary 角色后通过，未修改产品。
- 相同源码的 148 项单元、TS/Vite 和 13/11/6 组隔离浏览器结果沿用上一轮已通过证据，本轮未重复运行。主要源文件 Hash 再核对一致，`git diff --check` 通过。
- CAS/乐观更新：原 148 项回归及已有独立可重置数据集的真实 CAS 回执保持；本轮只读，没有再次 PATCH 或重做双会话写入。固定真实 Obligation 根未被用于 CAS。

## 交付状态

我方已完成静态截图及真实页面的布局/状态复核，本轮 live 联调 PASS。尚待用户对六页最终视觉的确认，以及是否提交/推送 `codex/uiverse-ui-upgrade` 的明确授权；本回执不是授权，也未执行 Git 上传。

本地现在可独立打开当前动态首页、新建扫描、真实历史和上述三个验收数据空间。未新增正式生产能力；生产 NOTICE、人工适用性审核、正式运行镜像、旧 v6 Formal、正式评测/Gold 和最终作品发布仍按团队既有门禁处理，不能以本轮 UI 签收替代。原接收材料不重复索取。

精确 token 数不可获得；开工估算 5,000—12,000，本轮完成恢复、只读验收及回执，实际是否位于估算区间无法核定。
