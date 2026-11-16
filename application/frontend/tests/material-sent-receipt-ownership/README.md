# 已发Material回执归属专项（SOURCE_ONLY / NOT_RUN）

本目录只新增独立测试源码。四个产品文件和24份冻结测试不改、不复制；实际产品和fixture从已建立接收快照的固定相对路径导入。没有执行测试、TSC、构建、Vite或浏览器，JUnit=null，PRODUCT_PASS=NOT_ESTABLISHED。

## 实际调用及封闭边界

真实React挂载同一P2Workbench实例，填写真实MaterialForm，合成File只控制arrayBuffer等待；原materialBytes执行UTF-8/base64及WebCrypto SHA256，原write/prepareWrite/submitWrite/request进入底层封闭fetch。Material POST先进入独立ledger并挂起其Response，不能通过替代整个Service制造通过。

transport无原fetch fallback或上游；GET只接受当前合同固定路径，非GET只有原A的一次materials POST。未知请求和全部非GET独立存档，产品catch不能吞掉账本失败。另设不计入产品场景的未知GET/DELETE账本自检。

## 八条测试源码场景

1. 原scope不变，已发201合法正控，准确接纳一次，不自动重放。
2. A已发POST后切B，释放201，B的Result、success、固定URL、pending及写错误不受A污染。
3. A→B→A精确原Binding、原Result归来后接纳原有效201。已发请求不受未发许可epoch的一律拒绝规则支配。
4. A→B→同一Assessment A、但固定Result不同，旧201不能覆盖当前scope。
5. A→B→同一Assessment A、但完整Binding及固定Result身份不同，旧201不能覆盖当前scope。
6. A已发409时当前B不出现A错误；Service保存原A conflict及原pending；返回A不重建、不自动重放。
7. 精确ABA返回A后409表现为原A冲突，不能显示保存成功或覆盖旧Result。
8. 发送前File挂起再ABA切scope，释放读取并明确观察原form finally，新增POST及全部非GET为零。

八是本次编写的场景数量，不是已通过的数量。

## ABA条件与公开入口限制

已发成功依照当前Service校验捕获的原Assessment/Binding/PendingWrite，并清理原attempt；Workbench再比较当前完整materialScope是否等于原scope。精确ABA允许原有效回执，不擅自增加epoch拒绝。未发File许可则比较提交epoch，ABA不会复活。

当前接收组件仅在Assessment id/version或reload改变时重新加载Binding/Result，busy时刷新按钮不可用。因而场景4、5用真实A→B→A effect重新加载，明确属于“同Assessment返回后的scope变化”，不冒充busy期间有一个现存的直接Binding刷新入口。Binding变化是有意构造的TEST_ONLY结构重载挑战，同时使用不同Result ID/Hash；它不能独立隔离“同一不可变Result ID只变Binding”的合法路径，该路径当前公开接口未建立。场景4使用独立并发r3，原材料回执是不同ID的r2；每个固定ID始终映射一个对象。所有重复十六进制Hash均为明示合成DTO标识，不是独立重算生产selfHash或输运认证。

Material WriteBody/PendingWrite没有独立requestId字段。测试保存同一个PendingWrite对象引用、serialized原字节、idempotency_key、parent_result_id与expected_revision；输出requestId=null、NOT_A_PUBLIC_FIELD。ledger sequence只是采集序号，不冒充requestId。

## 完成信号及失败分类

底层响应被实际request.json消费后，继续等待可观察的真实UI提交：切B/变scope时等待MaterialForm fieldset重新可编辑（来自原submit finally释放busy），或实际Result/URL/success/写错误变化后立即核对归属，避免把已发生污染却导致form消失误记为仅未settled；原A成功等待固定新Result及真实成功文案；原A冲突等待真实409错误；未发控制等待已脱离原form的aria-busy=false且buffer已释放。绝不只用setTimeout结束或保留Promise不释放。

5秒watchdog仅标记NOT_ESTABLISHED并停止套件，不当成产品红灯。每案teardown保持fetch封闭，卸载真实root，释放File/Response并drain；任何未知请求或额外非GET在独立账本升为失败。已切scope后busy/lock正常释放不算B污染，不断言B整段HTML完全不变。

## 未来执行条件（本轮不实施）

必须先获得实际runner操作者、入口、有效工具许可、生效禁外网、TASK限写、已有兼容React/Vite等依赖身份。准备的vite.test.config.ts只声明TASK与固定接收源码两处只读入口，不加载.env，无proxy、不开HMR、cache/outDir仅TASK；这些声明不构成原生隔离或依赖兼容证明。依赖须已合法存在并受控放在未来TASK指定目录，配置缺件直接报错；不能安装或借Owner node_modules绕过。

未来环境变量：OPENGUARD_SENT_RECEIPT_TASK=本轮精确TASK；OPENGUARD_APPROVED_FRONTEND_DEPENDENCIES=其内经验证的既有依赖目录。运行前重核本轮源码及被引用的产品/fixtureHash，缺件/漂移停止。不在本轮启动配置、server或浏览器。
