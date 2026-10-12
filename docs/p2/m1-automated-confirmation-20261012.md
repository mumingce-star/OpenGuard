# M1 自动核查回执（2026-10-12）

状态：**PARTIAL**。当前用户授权自动核查三项内容；本轮按当前工作树与固定 Git HEAD 读取证据，不修改M1正式对象。自动检查16组通过。机器回执：[JSON](m1-automated-confirmation-20261012.json)。

| 核查项 | 由现有证据自动确定的内容 | 尚不能确认为事实的内容 |
|---|---|---|
| 实际用途 | 仓库中作为扫描组件识别、npm元数据响应校验、许可证材料与绑定核对的测试/演示对象；前端manifest/锁文件无此依赖，tracked源码未发现包导入 | M1的七项业务用途仍全null；缺M1精确输入manifest，不能借用另一scan的受控测试用途 |
| 随作品交付范围 | 当前tracked有测试manifest、样例生成/校验代码与验证记录；未见包源码目录或tgz。Docker配置含tool-smoke.py样例声明及npm校验器，Web最终阶段复制dist，tests/docs不进入Docker白名单 | 未检查最终镜像或交付manifest/SBOM，不排除扫描工具/基础镜像内的副本；M1范围仍NOT_DECIDED |
| Owner指定许可审核人 | 旧交接将cz/授权审核者列为补件责任方；本轮自动技术核查者为GPT-6 Codex | reviewer/date/scope仍null。责任分工不证明Owner任命、真实审核或签名，本轮指令也未给出被指定人的身份 |

## 证据与对象边界

- M1：scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d，asm_6c664ed7-7c41-512c-bbcc-a178a8edea79 v1；资源cmp_1fc87b46-9132-51b6-b39e-bf1af669ca8a@7.0.0，Material/Result精确ID及原输入摘要见JSON。
- M1原始用途和审核状态：[原件读回](p2b-npm-original-readback.json)，/M1/usage、/M1/user_assertions、/human_review；原件本轮未重新验包，既有30组检查不计入本轮。
- 仓库用途：tests/fixtures/syft-real/package.json及package-lock.json；tests/unit/test_b3_syft_real_output.py；deploy/tool-smoke.py；deploy/smoke.py；backend/app/p2b/npm_metadata.py。
- 三例生成器tests/fixtures/p2b/run_three_scans.py只写package.json/package-lock.json；旧is-number样例scan=scn_761868e1-b9fa-4225-af23-d05c93d7b80f，与M1不同。同resource ID不能代替scan绑定。
- 交付配置：deploy/Dockerfile.web、deploy/Dockerfile.scanner、.dockerignore、.gitignore。当前前端锁文件无is-number。源码manifest里的依赖声明不等于交付了包代码。
- 任命定位：m1-local-evidence-blocker-20261011.md明确cz确认链缺失；p2b-next-task-plan.md人审reviewer/date/scope为空。未发现可读已签署任命记录；此结论限当前搜索集合。

## 验证范围与限制

扫描752个tracked文件的字面量和可执行源码的包导入模式，固定19份当前输入的SHA256与大小；全部匹配文件/行号见JSON。静态检查通过只能证明以上内容，不证明生产调用、最终包内容、完整历史语义审计、合法适用性或义务履行。

运行的是本轮Node内存静态核查；未运行目标代码、产品测试、扫描器、模型或服务，没有业务数据库写入。未新增依赖、复制第三方原文或改动旧回执。新JSON是内部核查工件，不添加公共接口/Schema字段，不生成新的业务Evidence或Formal许可结论。

## 尚未关闭的三项门禁

1. Owner/A：提供或建立同一M1输入、用途与版本关联；商业、修改、分发、网络服务、训练、资源再分发及源码开放不能从包名推测。
2. Owner/交付维护者：实际最终交付manifest或镜像SBOM与排除项，区分声明/样例代码和第三方包原字节；当前配置确认不是发布物确认。
3. Owner/指定审核者：真实被指定身份及审核记录；允许unknown/pending/拒绝，无需强求肯定许可结论。自动技术核查结果可作为输入，不能代替真实指定与签认。

本轮新增两份脱敏本地核查工件及治理追加，未stage/commit/push/merge/deploy。当前codex/scan-reliability-integration@50d8704a362f6e6615c1ed95d7f06da2bc3e871f；旧功能分支发布与本轮未发布分开，M1产品运行和最终发布未执行。

本次运行精确 token 数不可获得；开工估算6,000～12,000，自动静态核查已执行，三项正式确认仍PARTIAL，范围未扩为产品运行；实际是否在估算内无法核定。
