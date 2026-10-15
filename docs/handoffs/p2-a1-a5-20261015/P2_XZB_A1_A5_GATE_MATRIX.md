> GitHub脱敏发布副本：本地原件保持不变。本文中的历史文件路径仅是来源定位，并非本次附带的GitHub文件；本次仅上传同目录五份交接文档，不含源码包、运行镜像、数据或历史证据附件。原件与发布副本身份见本目录Manifest及Git提交。

# A1—A5 门禁与责任矩阵

证据等级与交付状态分别登记；历史发送机验证不等于目标机验证。

| 项目 | 本轮证据 | 当前状态 | 能否交xzb | 唯一下一输入/门禁 | 责任人 |
|---|---|---|---|---|---|
| A1前端源码 | 最新需求原件已核验 | BLOCKED_MISSING_SOURCE | 缺件索引可交 | 81原件+清单算法 | xzb/A |
| D1静态回执 | xzb已做声明；原回执未到 | 等待独立核对；不否定已做 | 可交状态说明 | D1及最新原回执/源码对应 | xzb提供，A核对 |
| 统一候选 | ZIP/44清单/731源码Hash一致 | READY_TO_REFERENCE | 可直接引用旧包 | 接收机签收 | A/xzb |
| 运行镜像 | 本机镜像、已有tar及OCI身份 | LOCKED_RUNTIME_IMAGE_UNAVAILABLE（完整组合） | 身份可审，分发待决 | 架构/源码组合/第三方分发批准 | A/Owner；目标架构xzb |
| 固定ID与合同 | 三例、九类固定GET/例、合同DTO | READY_TO_REFERENCE | 是 | 接收机27GET和重启 | A/xzb |
| 隔离只读副本 | 发送机历史根；接收配置提案 | TARGET_MACHINE_PENDING | 仅提案 | 获准后接收机新私有根及地址 | A提供配置，xzb执行 |
| 隔离写入副本 | L2合同及独立根方案 | REQUIRES_OWNER_AUTHORIZATION | 仅提案 | 新可重置根获准范围 | Owner/xzb |
| Git/ZIP输入 | 固定bundle与三ZIP字节已核验 | READY_FOR_STATIC_REVIEW | 可引用 | 统一候选启用条件与扫描授权 | A/Owner/xzb |
| cz六文件 | 7caddf4六Git blob全部匹配 | READY_FOR_STATIC_REVIEW | 固定Git对象索引 | A限定接纳新pin | cz/A |
| npm材料接纳 | 原件/发行包/成员及历史工厂HTTP | HISTORICAL_SENDER_VERIFIED | 是 | 正式受信来源与新增事实 | A；cz技术材料 |
| 人工适用性 | 七用途null；范围NOT_DECIDED | WAITING_FOR_SPECIFIC_INPUT | pending记录可交 | 真实用途/范围及审核理由Hash | Owner指定审核人 |
| 旧v6 Formal | 同Scan扫描报告不是v6 | OLD_V6_FORMAL_ORIGINAL_MISSING | 可交缺件说明 | 原JSON/HTML及共享许可或保留限制 | 原件持有人/Owner |
| NOTICE窄修 | xzb433/433声明；旧JUnit已核验 | INTEGRATION_NOT_VERIFIED | 缺件索引可交 | 已有diff/JUnit/候选/维护者纳入证明 | 维护者/xzb |
| 目标机验收 | 本轮未执行 | TARGET_MACHINE_PENDING | 接收步骤可交 | xzb实际环境/请求/浏览器回执 | xzb |
| 最终签收 | 本轮只读证据 | PENDING_OWNER_DECISION | 供独立复核 | Owner独立决定 | Owner |

## 与D1分离的生产门禁

| 门禁 | 本轮状态 | 下一步与责任 |
|---|---|---|
| 生产NOTICE | 未凭fixture修复升级 | 维护者原件与集成审查；生产适用性单列 |
| M1可信来源/实际适用性 | BLOCKED_REAL_MATERIAL_OR_BINDING_MISSING | A来源接纳与新增事实，Owner范围，指定审核者人审 |
| P2独立真实用途建议 | 未建立生产接受 | 独立录制chalk条件候选不等于统一P2正式新用途建议 |
| 完整live runtime | NOT_ESTABLISHED | 本轮未读权重、未重试Profile |
| A04覆盖传播 | 原交付BLOCKED_OFFLINE_TEST_ENVIRONMENT | 可用环境或单独容器/依赖授权；此任务不修复 |
| B03新pin | 7caddf4原件已到，统一ec4c未包含 | A按实际两模块差异限定接纳 |
| 最终Owner验收 | PENDING_OWNER_DECISION | Owner独立复核 |
| 参赛/产品发布 | NOT_GRANTED（本任务不新增权限） | 任何此前特定提交许可不等于产品发布许可 |

## 真正需要Owner决定的事项

1. 现有镜像第三方分发范围，以及接收架构不匹配时是否授权最小重锁定。先让xzb报告实际宿主/engine架构。
2. 两新私有根、服务启动及L2/扫描的执行范围；已有明确覆盖的授权可沿用，本轮不自动执行。
3. M1真实用途/交付范围和有权审核者；保留null直到真实回答，不由Codex代签。
4. 若旧v6持有人仍无法提供原件，是否接受该项保持缺件限制；其他前端工作继续。

81文件、D1回执和NOTICE旧窄修补件是对应持有人的材料交接，不要求Owner替他们重新测试或重新推送。尚未获得目标机回执前不请求Owner签产品PASS。
