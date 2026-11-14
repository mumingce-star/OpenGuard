# P2四文件跨特征测试源码

状态：**NOT_RUN**；JUnit=null；PRODUCT_PASS=NOT_ESTABLISHED。

本目录是新增专项，不是原两组各自测试的相加。真实挂载`P2Workbench`及其内部`ProjectUsageEditor`，调用真正的`projectUsage.ts → ensureP2 → p2.ts → fetch`。只替换底层封闭transport；不替换React hook、组件、continueUsageUpdate、ensureP2或submitWrite。不启动ASGI，不代表xzb接收或真实后端保存。

## 安放范围

未来获准的完整独立前端副本中：四个产品文件采用本包candidate/after；两组原测试按原路径完整放置，本目录放`tests/p2-integration-boundary/`。fixture复用原`bound-advice-maincard/fixture.ts`，不会修改它。其他产品依赖仍须由完整副本提供。本包不是完整可启动前端，不安装依赖。

`vite.test.config.ts`只为未来获准runner准备，不是运行许可或OS隔离证明。它使用TASK/runtime/frontend、envDir=false、独立cache/outDir、127.0.0.1、禁HMR及明确API开关。本轮没有执行或加载该配置。不得对原源树或现有服务使用它。

## 七个跨特征场景

|源码场景|观察边界|
|---|---|
|同Workbench Advice＋readOnly pending入口|保存条件仍可见，嵌套Editor不可提交/恢复，新非GET为0；历史seed POST另计|
|Index挂起→同实例readOnly提交→释放|真实saved-next Assessment Index挂起；Profiler mount次数与DOM引用检查同实例；Result POST调用及全部非GET双重检查|
|ordinary loading disabled仍明确恢复|真实Workbench refreshHead的旧Assessment Index挂起形成loading；字段disabled而恢复按钮可用；另一个Assessment Index释放后观察真实Result fetch调用、原幂等key和pending|
|新用途草稿→readOnly→submit|先真实修改radio，再同实例提交readOnly；直接派发form事件核入口；不创建pending或新请求|
|同Workbench r1→显式r2，旧derived晚释放|真实固定GET与refreshHead；旧请求遵从AbortSignal，核r2主卡与URL、不串r1条件；不宣称无视abort的恶意transport已覆盖|
|derived503＋pending只读保护|automatic-review错误可见但保存Result/Advice保留；只读恢复仍被保护|
|混合basis＋只读主卡|复用直接scope＋间接license_text结构，显示准确未核验说明，不生成许可肯定或禁止结论|

主卡的原G1/G2/G3细分回归仍在原冻结专项中，原12文件一字未改。本专项不代替那些回归，亦未运行它们。

## 请求与时序

两个Index由精确Assessment ID及query区分：主卡父评估version=1有r1/r2；用途恢复指向新的合成Assessment version=2，空head供Result初次创建。两者不混成一个gate，不把Assessment.version当Result.revision。

pending通过真实beginUsageUpdate与submitUsageUpdate产生；seed使用合成202而非直接改内部Map。恢复时真实job GET、Assessment GET、Binding GET与Index GET到达transport。Result POST对照记为真实前端fetch调用，随后抛出明确的回执不确定错误；不伪造201/409/405，不把它称服务器成功/拒绝。撤权场景必须没有此调用。原requestId最高79字符，符合现行8–90契约；底层记录完整原request body，不按JSON键顺序判用途相等。

独立`ledger/unknown/nonGet`先登记再拒绝，未知或被产品catch的请求也会使场景失败。自检使用独立transport账本，DELETE/未知GET只是合成捕获器自检，不混算产品请求。读取/解析不合法也登记拒绝；无原生fetch回退/上游代理。该机制不是全OS网络约束，未来仍须外层获准隔离。

禁止全局fetch恢复后放走晚到请求：源码明确让封闭transport保留到测试页销毁；每案先卸载，再释放gate并等待在途响应。watchdog失败终止等待循环，不转换成通过。全suite失败即停止，错误及账本仍保留。唯一受控入口是页面按钮/导出的run函数，本轮未点击、未运行。

## 静态修订与局限

独立静态审查发现并修正的是**新测试源码**：长标签导致requestId超限；watchdog外层拒绝后内部循环仍继续；URL/JSON解析错误需在独立账本中保留。当前可保留的修前五文件及Hash和最终diff在test-source-review-history中；首次草稿的早期修改未另存完整原流，不能据此声称全编辑历史均已捕获。

没有运行TS解析、类型检查、组件测试、构建或浏览器，没有加载模块trace。所有情景是待执行设计，实际场景结果为空；源码中的passed赋值只属于未来运行程序，不是本轮结果。

未证明成功POST后的导航/合法成功回执、StrictMode或全部其他异步材料路径；不新增这些产品能力。不认证真实http-server材料、用户用途、来源、许可适用性或义务履行。真实对象缺口继续保留。
