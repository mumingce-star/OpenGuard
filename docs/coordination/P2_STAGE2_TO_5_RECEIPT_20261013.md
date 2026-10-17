# P2 阶段2至5前端实施与验收回执

本轮按用户明确授权并行完成当前可独立的前端工作，不等待扩展整包签收。原计划步骤12—33仍逐项记录，没有将前端测试通过写成真实后端闭环完成。

## 阶段结果

| 阶段与步骤 | 当前本地成果 | 验证等级与未完成项 | 责任 |
| --- | --- | --- | --- |
| 2，12—16 | 沿用已实现的固定Result读取、首屏资源用途、条件/gap/Evidence、错误/空/partial/重试 | L1聚焦8项测试PASS；已有回执静态相容；真实实例签收待运行 | xzb执行；运行输入由Owner协调 |
| 3，17—22 | 已有回答/小材料、CAS、幂等恢复；本轮补新旧快照原值核对、只读请求防护、敏感材料提示、打印可读性 | L2及版本聚焦12项测试PASS；TEST_ONLY浏览器交互PASS；真实写入和重启待隔离实例 | xzb执行；A提供获准配置 |
| 4，23—28 | 可复跑浏览器回放脚本、负向/版本/刷新/窄屏/打印证据 | PARTIAL：本机8082连接拒绝；没有真实Git/ZIP、CAS、重启、下载Hash签收；不改固定数据 | xzb，依赖Owner运行交付 |
| 5，29—33 | 完整前端测试/构建、源码身份、操作说明、3分钟演示、两份总需求 | 本地交接已整理；最终真实演示、Owner审核和发布仍待；不声明整个阶段5 PASS | xzb整理；Owner复核 |

## 本轮改动

- `frontend/src/components/P2VersionComparison.tsx`：显式GET指定前版，父绑定/版本/数据等级核对后并排展示原值；重算与复用只转述后端字段，不计算第二套差异结论。
- `frontend/src/components/P2Workbench.tsx`：接入对照、材料敏感信息提示、P2只读交互。
- `frontend/src/services/p2Workflow.ts`：前版读取及只读写入拦截。
- `frontend/src/styles/workspace.css`：窄屏列布局与打印黑字白底，保留快照正文、隐藏提交控件。
- `frontend/tests/p2-workflow.test.mjs`：新增5项版本、只读、材料边界和错绑/重复提交测试。保留上轮竞态测试。
- `frontend/tests/p2-browser-fixture.mjs`：独立浏览器测试，所有API请求被拦截，非允许请求失败；从已收回执和原LICENSE构造测试，不进入应用真实模式逻辑。
- `frontend/tests/p2-source-manifest.mjs`：生成不覆盖旧文件的完整源码Hash，不伪造兼容commit。
- 两份总交付需求和本回执；共享日志、进度仅追加。原有未提交前端、NOTICE单测和协调文档全部保留，不清理或上传。

未改后端、公共Schema、依赖或数据库。没有从外部引入UI资源，使用现有React组件/样式；沿用锁文件及构建生成的 `third-party-licenses.txt`。AI辅助范围为前端实现、测试与交接撰写，结论由测试核对；没有模型API调用、许可人工签认或Formal改写。

## 验证与证据等级

- `node --test tests/p2-advice.test.mjs tests/p2-workflow.test.mjs`：20/20通过。
- `npm test`：142/142通过，0失败、0跳过；复跑不重复累计。
- `npm run build`：TypeScript noEmit和Vite生产构建通过。仓库没有独立lint脚本，不报告lint通过。
- 已交HTTP回执：Summary/Answer/Material各3份通过当前校验器，STATIC_RECORDED_HTTP，不是活接口。
- 浏览器回放：11项检查，78个拦截请求，其中4个模拟POST，0真实后端写入、0pageerror、0未声明API；包括503、网络未知态、原键重放、409重读、新版读回、前版失败重试、390px/键盘/reduced-motion、打印正文、旧URL刷新只读。不是实际CAS/持久化证明。
- 原交付请求中的material content_base64是脱敏占位符；测试改用包内npm LICENSE原字节并核对 SHA256 `35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2`，不把占位符当材料。
- 浏览器调试前五轮失败记录保留：前3轮缺少P0四格式预期错误适配，第4轮标签精确匹配错误，第5轮误将材料占位符当base64。均为新测试脚本问题，未通过放松产品校验解决。第6轮通过后视觉检查发现打印引言对比度不足，已修复；第7轮最终复跑11项PASS，打印截图已目视核对为黑字白底且保留完整快照正文。
- `http://127.0.0.1:4182/` 本地预览200；`8082`固定Scan GET为ECONNREFUSED。没有启动/替换后端，不重复安装镜像。4182已有进程，严格端口启动被拒绝后直接复用，不杀进程或占用其他服务。

### 证据索引与源码身份

- 当前81个前端文件完整清单：`docs/coordination/P2_FRONTEND_SOURCE_20261013.json`；逐文件复算81/81一致。聚合SHA256：`c92a2143f1cdc46f903089f22237a62b95f183f75dd0111b78bfa991d5a732bd`。算法在清单内，基准HEAD `9ad9998d6f3df82618966c5865d13006a1efe6bc` 不是未提交工作树的完整身份。
- 最终浏览器回执：`tmp/p2-stage2to5-20261013/browser-7/receipt.json`；同目录 `test-only-version-pair.png` 与 `test-only-version-print.png`。tmp为本机忽略目录，不上传真实交接材料或截图中的私有来源。前6轮输出留在各自目录，未覆盖旧证据。
- `git diff --check`通过；后端业务、Schema、package/锁文件本轮无差异；新产品/脚本/交付文档的常见凭据及本机绝对路径模式扫描无命中。该扫描不是完整安全审计。
- `VITE_P2_READ_ONLY=1`在服务和SSR测试已覆盖，未另启只读构建浏览器实例；实际后端只读拒绝仍待真接口验收。

## 本地复现

先在frontend使用已有依赖执行 `npm test`、`npm run build`。如果4182无人使用，可执行 `npm run preview -- --port 4182 --strictPort`。代理依已有Vite配置使用 `OPENGUARD_API_PROXY_TARGET` 或 `OPENGUARD_P1_API_PORT`；不要把测试回放当成后端。

只读P2构建：PowerShell设置 `$env:VITE_P2_READ_ONLY='1'` 后build；恢复可写候选前删除该进程变量并重新build。此开关仅保护P2提交，不是全应用鉴权，扫描/Assessment等服务仍需后端只读配置。生产服务端应始终独立做鉴权、CAS和只读限制。

浏览器测试从frontend运行：

```powershell
# 以下路径由本机已有文件填写，不下载或安装依赖。
$env:OPENGUARD_PLAYWRIGHT = '<已有Playwright模块的绝对路径>'
$env:OPENGUARD_TEST_URL = 'http://127.0.0.1:4182'
$env:P2_HTTP_EVENTS = '<已收统一包>/evidence/http-events.json'
$env:P2_MATERIAL_FILE = '<已收统一包>/sources/npm/is-number-7.0.0/member-1.txt'
$env:OPENGUARD_QA_OUTPUT = '<项目下一个全新证据目录>'
node tests/p2-browser-fixture.mjs
```

测试会逐项校验请求；原字节材料Hash不匹配直接停止。脚本不得连接非本机预览，也不会将API请求放行到真实后端。输出receipt标记TEST_ONLY，不支持把它改成LIVE通过。生成源码清单可在仓库根执行 `node frontend/tests/p2-source-manifest.mjs <新的manifest.json>`，目标须在frontend外且不存在。

真实验收时关闭所有route fixture：先核镜像/源码/ZIP身份，在全新私有根恢复，同ID GET和重启复读由xzb执行；只读固定样本和可写CAS副本分离。真实扫描/外网操作需Owner确认范围。本轮未操作这些事项，先保留PARTIAL，不自动POST、init、apply或更换结果ID。

## 三分钟演示脚本

1. 0:00—0:25：说明数据等级及真实/回放边界，展示Git/ZIP用途三态；当前未运行真实扫描时明确说“输入界面与透传已有，跨栈尚待验收”，不点击模拟结果冒充实扫。
2. 0:25—0:55：显示固定Scan、Assessment版本和Result，讲解未知、候选、必要条件与Evidence，不能说已获许可。
3. 0:55—1:35：在获准可写副本提交明确资源子集的回答/小材料；当前仅可演示TEST_ONLY回放，说明未经核验和敏感信息限制。
4. 1:35—2:05：显示新版Result、同版摘要、指定前版并排原值；指出Formal Assessment版本与原报告不被改写，重新计算不等于结论改变。
5. 2:05—2:35：展示旧URL刷新只读和网络未知态的先读取、后原键重放；不自动创建第二请求。
6. 2:35—3:00：展示390px和打印正文，说明剩余真实实例、重启、人审和生产NOTICE门禁，结束。

必要截图：L1首屏与完整身份、Evidence/gap、提交未知态/冲突、新版Result及summary、前版并排、旧URL只读、窄屏、打印正文。截图注明TEST_ONLY或真实实例，不混用等级。

## 汇总边界

本轮可独立运行的是前端预览和TEST_ONLY交互回归，不能独立证明P2真实后端闭环。原D1已有静态交付，待Owner复核；扩展B1—B5和后续生产能力单独登记。参赛资格/材料由Owner核实，完整作品仍需真实跨栈签收，竞争力还需质量、性能和演示实测。本轮没有定义完成百分比，也未提交、推送、合并或部署。
