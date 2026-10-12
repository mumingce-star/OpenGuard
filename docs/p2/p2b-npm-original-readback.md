# 后端 B：实际 npm 原件到件与 M1 增量核对

日期2026-10-12；原字节核对 **PASS**，整体 **PARTIAL**。用户已转交原始npm元数据、发行包、成员、历史获取回执和M1材料/人审片段，撤销当前“原件未到件”停止点。旧报告保留当时事实，不覆盖或回填。机器证据见 [读回回执](p2b-npm-original-readback.json)。附件是资料，不执行其中产品接线/服务/迁移指令。

## 已独立核对

- 元数据：is-number@7.0.0，3199 bytes，SHA256 42288c4971286c252ea16450b0777e67a710a698446faa99e2d8d2344a087c25；历史URL https://registry.npmjs.org/is-number/7.0.0，UTC 2026-10-11T04:20:01.770081+00:00，HTTP200。license=MIT仅为provider声明。repository与dist字段已核对。
- 发行包：3730 bytes，SHA256 7b75c1057198cf97696909a9bee176c9c5e9bcb5b03bf3ecef2f484defadd51e；UTC 2026-10-11T04:20:02.661901+00:00，HTTP200。SHA1和SHA512 SRI均与原始元数据一致；包内4个普通文件，共9615 bytes。包成员逐字节匹配转交的package.json与LICENSE，不安装/执行包代码，不落盘解包。
- LICENSE：1091 bytes，SHA256 35bdd8a44339719441900fb50fbefc5e2dca1ca662cbaed7a687de842c8b70f2，确为本次精确发行包package/LICENSE成员，原文Hash也与旧B观察一致。四锚点及byte/line/唯一性在本次实际原件上重新核对。它们是文字锚点，不是完整条件边界或人工适用性签认。
- Manifest登记9个文件的大小/Hash全部匹配，第10件Manifest自身Hash单独记录。3个片段长度与声明的父字节区间一致；父文件未提供，其Hash及“精确截取”归属仅记录为转交方声明，不冒称独立重算。

## M1完整绑定已到件

Scan scn_fb8856de-91c3-41b7-b758-fcf35c2ea77d；资源 cmp_1fc87b46-9132-51b6-b39e-bf1af669ca8a@7.0.0；Assessment asm_6c664ed7-7c41-512c-bbcc-a178a8edea79 v1。

Material p2mat_c5090e4fd86a58311fab75962e7d545057d2e8b028c358d467f764b225e0c61b revision1；Result p2res_eabfaa020c8a91cd4a5a309861ad4f0ab90cae07263d4ac48370b8a02b89fc83 revision3；前驱 p2res_c3dd21f24d2f94df3f09ebb47f0d15ffd38ee05e8dbead64530c43f6e6037040。Result canonical摘要 00c297c662b1ad5efadbc6e92fe2d2401a6b53d555013c497427457ce74a7dca 已复算。完整Binding/Hash、实际Material引用的1个Evidence、资源闭包2个Evidence、精确GET及JSON Pointer均在机器回执/M1字段保留。

当前前端验证器接受这个历史Result和Material，仅为离线结构接受，不代表接收机HTTP签收。Summary只有ID p2sum_e16fe5df4395f6fea3abb83a00ca1d6d26cdf048f9e6d0b3b09a9b409979ff4a，未提供正文；Answer亦只有ID，不冒称闭包全部取得。

七用途全null，交付范围回答NOT_DECIDED，Material保持pending/user_supplied_unverified；advice.rule_ids与basis为空。此M1链与旧三例is-number扫描/Assessment不同，禁止跨scan借用ID或用这份来源记录自动升级旧材料。

## 五项技术补件增量

1. producer/来源：现已核对npm响应声明及精确发行包→LICENSE原字节关系；传输回执提供URL/UTC/HTTP/headers/大小/Hash。请求方法/final URL/redirect_count/timed_out/policy/验证器身份未明确保存，A正式受信签发仍未完成，B不自签。
2. 条款索引：许可[68,112)第5行；声明保留[502,573)第12行；免责声明[630,662)第15行；责任限制[832,892)第17–18行。本轮实际npm成员复核PASS，不导出正文。
3. 适用范围：包版本与成员归属已核对，但真实用途/交付集合/排除项及许可证适用性/义务履行仍Owner和指定审核人确认；reviewer/reviewed_at/scope为null。
4. 自然缺口/错版：全归档未发现NOTICE成员，仅能说明文件缺失，不能推导无声明义务。同包真实另一版本对照本次未提供，不新抓取或合成冒充。
5. 相对旧r3：新增是技术可读性、获取记录/完整对象到件及本轮独立字节关系验证；原LICENSE已在旧材料保存，不新增业务事实/Evidence/许可正向建议，也不重复保存。

## 仍待的独立门禁

A负责正式来源接纳、缺失传输字段/策略/验证器及Evidence物化/存储/coverage；Owner负责真实用途和范围、M1 STOP续接决定；指定审核人负责完整条款/适用性/履行签认；A/保管方补完整旧Formal及同版Summary，前端在获准运行组合和数据根做真实读取/写入签收。材料到件不自动解除M1 STOP。

本轮30组检查PASS，网络/服务/数据库/模型/安装/执行代码均0。源码/公共Schema/规则与旧业务记录不变；附件原字节、Owner本机绝对路径及第三方全文/归档没有复制到仓库。两份新增脱敏读回仅本地，未提交、推送或部署；公开发布授权尚未授予。
