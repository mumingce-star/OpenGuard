# 材料异步读取后撤权：冻结测试源码

当前状态：`TEST_STATUS=NOT_RUN`、`JUNIT=null`、`PRODUCT_PASS=NOT_ESTABLISHED`。本目录六文件是待获准runner验证的源码，不是产品测试结果、浏览器接收或新运行许可。本轮未import此配置、测试或产品代码，未执行Vite/TSC/测试/HTTP。

## 实际被测边界

采用真实`P2Workbench`及其内部`MaterialForm`、真实`materialBytes`、`prepareWrite`和`submitWrite`。不替换这些函数、React hook或组件。只替换最底层`window.fetch`；它没有native fetch回退或真实上游。合成File只将`arrayBuffer()`暂停，其他UTF-8检查、base64与WebCrypto SHA-256由真实Service执行。

`fixture.ts`复用冻结的`../bound-advice-maincard/fixture.ts`；这一原文件以及其他原18份测试保持原字节。新fixture、用途、Evidence、请求响应均明确为`SYNTHETIC_TEST_ONLY`，不是http-server真实LICENSE、生产Scan或正式来源。文件内容为118字节合成文本，SHA256=`2b22f17bf8862c1595b800b3be3d6a632358dada825973a5a40384b4a0dcb106`。

未来完整隔离前端副本须保留现有依赖与其余产品源码，只在父本/候选两份副本间切换冻结产品字节。新测试六文件及原18文件必须同字节；本目录配置的路径检查只是防误用，不能证明网络/文件OS约束，也不能代替实际工具许可。没有这些凭证不得执行。禁止用此配置启动Owner原树或安装依赖。

## 十个场景及真实时序

所有场景在同一真实Workbench挂载中填写准确资源、直接Evidence、合成File和来源说明。读取类场景派发真实表单submit，先确认`File.arrayBuffer()`已经进入且Promise尚未释放；第9项专门在填写完成后、submit之前提交readOnly，要求File从未开始读取。

1. 同一实例提交`readOnly=true`，再释放文件读取；Material POST及全部非GET为零。
2. 分别提交`false→true→false`，旧File的资格不得复活。
3. 通过现有History分页获取并发保存后的head，再明确点击读取固定r2；旧r1的MaterialForm因Result key变化卸载，旧File不能提交。不是注入setState，也不拿latest替代固定GET。
4. 在同一个React root提交另一套准确Assessment/Binding/Result，读取该固定Result后释放旧File；旧工作不能写入旧或新scope。
5. 真正unmount根，再释放旧File；使用捕获的已脱离form观察finally结束，不靠节点消失声称异步已结束。
6. 点击真实“补充项目用途”切走材料tab；Workbench同实例仍然挂载，只有旧MaterialForm卸载。释放旧File后，独立form生命周期撤权仍须阻止POST。
7. 始终可编辑且身份不变，实际Service派发恰好一次Material POST，收到结构合法的合成201 Receipt；核CAS、parent、Hash、原字节、资源/Evidence、材料pending及真实成功UI。
8. 先确认Material POST已实际派发并保存原PendingWrite，再提交readOnly，之后释放结构合法的合成Receipt。原serialized、幂等键、CAS/parent不重造；已发请求正常按回执结束，不追认为未发，也没有新POST。
9. 真实表单在可编辑态已填好，submit前提交readOnly，再明确派发submit事件。File.arrayBuffer调用数必须为0，Material POST／所有非GET为0，不能以未填写表单的提前返回冒充权限保护。
10. 可编辑稳定状态的真实Material POST已经派发，释放一份除Material.subject.version错为`9.9.9`之外结构合法的合成201。真实Service校验必须拒绝；主卡仍r1、没有成功UI，原pending serialized／幂等键／CAS保持，已发POST计1且无自动重试。write错误由其准确容器和提示观察，不把独立preliminary 503当成目标拒绝。

第3项初始Index明确head=r1，使真实材料表单可编辑；后续offset=1返回r2 head只模拟另一客户端的并发保存。此路径均通过真实已有按钮、Index Service和固定Result GET，不mock目标状态分支。

## 不能以未结束Promise制造通过

撤权场景先证明File等待已经entered，再释放buffer。单有`arrayBuffer`已resolved不足以证明后续SHA或提交链结束。

修复候选的真实表单在读取开始记录`aria-busy=true`，真实finally在最初捕获的HTMLFormElement上记录`false`，包括节点已卸载的情形。这是普通ARIA状态，不是global测试hook。测试等待其真实finally标记，之后再核独立请求ledger。

父统一after没有这个ARIA结束标记。因此同一测试源采用race：实际Material POST dispatcher已经进入，则记录真实越界派发并失败；否则只有曾观察到busy=true且finally=false才能确认本轮续接结束。父本缺属性本身不导致红灯。两者都没有时，watchdog记`NOT_SETTLED / NOT_ESTABLISHED`，停止整个suite，不能写成零POST通过，也不能把未计清的旧异步工作带进下一case。未来父本是否出现目标断言红灯只看实际ledger，当前不预填。

正常提交与已派发回执场景以真实Service接受Receipt后的固定r2及成功UI作为额外完成观察；结束前还等待封闭transport所有已记录inflight。5秒watchdog只表示未建立完成证据，不是产品红绿断言或超时安全结论。cleanup缺少预期POST只记未建立，不能覆盖原NOT_SETTLED；只有账本实际观察到额外非GET或未知请求时，才能升级为真实请求违反。

## 独立请求账本

每个fetch调用先写总ledger，再识别路径与方法；所有非GET独立记nonGet，未知URL/方法/查询独立记unknown。产品catch不能删除它们。唯一路由写入为精确Material POST，重试、其他写方法与未知路由均拒绝。自检在另一个transport实例发送未知GET/DELETE，单列`NOT_PRODUCT_REQUESTS`，不混入场景请求数。任何场景最终unknown非空、写次数不符都会失败。没有native fetch回退，也没有真实HTTP。

任何失败或未建立结束证据都会保存当例原ledger并停止suite，不会把可能未结束的旧续接带入下一例。未来父本若首个场景因真实POST失败，只能报告该实际失败，后续场景仍未执行，不能声称父本十项全红。

补入MaterialForm单独tab卸载场景前，六份新测试完整原文件及Hash封存于TASK的`audit/test-source-revisions/pre-tab-unmount/`；该次修改仅调整新测试，原18文件未改。修改diff随任务静态审查记录交付，旧版本不是运行结果。

补入权限入口和错版本回执两项直接负例前，六份新测试另封存于`audit/test-source-revisions/pre-negative-cases/`。准备表单和触发读取拆为独立helper，没有修改真实MaterialForm、P2 Service或旧18文件。

报告中的`passed/failed`字符串仅为未来执行后的真实分支，当前初始状态为NOT_RUN。没有生成JUnit，未来捕获器须保存实际浏览器/测试输出及真实退出，不得用源码Hash或配置存在替代执行证据。
