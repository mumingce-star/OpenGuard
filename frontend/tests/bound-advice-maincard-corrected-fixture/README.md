# 派生测试：unknown current usage fixture一致性补正

本目录由同TASK中的 `tests/bound-advice-maincard/` 六份源码逐字节复制，属于单独冻结身份的派生测试，不替换原24份冻结文件。

原冻结浏览器专项已实际运行：前4例通过，第5例 `unknown current usage` 因不合法fixture停止。原Result的 `/usage/commercial` 为null，但peer的 `/resources/1/advice/0/saved_value` 仍为true且selection为SELECTED；现行 `services/p2.ts` 第50行按合同拒绝该DTO。原始失败原流保留在 `attempts/frozen-browser-suites-20261021T090159Z-be6ca222/bound-advice-maincard/`。

唯一测试逻辑变化：将该例原先只修改target商业Advice的mutation，改为对Result每个资源的商业Advice同步 `saved_value=null`、`selection=UNKNOWN`、`state=unknown`。目标原条件文字保持，用于核对不会泄漏为许可肯定建议。全部断言、案例数、其余fixture、transport、配置和产品validator保持不变。

本目录准备时未运行任何测试或产品命令。后续必须独立记录实际运行结果，不能将新字节结果记作原冻结测试通过。

完整差异、原副Hash和断言保护记录位于本TASK的 `helpers/fixture-correction/`。
