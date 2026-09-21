# 12 条真实资源／风险记录复核表

日期：2026-09-09。范围：软件、模型、数据集、API各3条；仅复用既有真实报告，未重新扫描。当前 **机器关联检查12/12，人工复核0/24份**（负责人和cz各12份）。这里的0表示尚未收到记录，不推断真人是否已经线下检查。

## 如何填写

你和cz各自使用一份本表，先看原文件及上下文，分别填写“第一阶段”，暂不展开系统对照；都完成后再比较。候选由系统检出结果选出，类别和名称已经可见，不能宣称盲测或召回率评测。请填写是否曾看过系统输出。建议先提交自己的判断，再接收另一人的答案；不要把本表的机器检查当作人工答案。

填写头部：复核人角色【待填】；日期【待填】；此前是否看过系统风险/AI建议【待填】。

每条第一阶段：①原文中是什么对象、什么使用情境；②哪行/字段支持判断；③本段是引用、许可声明还是授权证明，依据是什么；④不确定事项。可明确写“无法确定”，不要凭项目根LICENSE给依赖、模型、数据集或API授权。

第二阶段展开系统对照后填写：资源识别【正确/错误/不确定】；证据关联【正确/错误/不确定】；风险措辞【接受/不接受/不确定】；AI建议【可执行/过于笼统/错误/不确定】及具体原因。任何证据串错、虚构、无依据授权结论或报告不可用均记录阻断；意见不同先保留双方原文，再写处理结果。

## 机器预核对及限制

- 12条都有对应资源、风险和AI建议；AI引用均落在本风险/许可允许的Evidence集合，34次Evidence引用对应25份固定原文件，Hash及报告已有行号片段检查通过。
- 软件未提供行号的Evidence保留原字段定位；下方行号是本轮人工阅读导航，不写回报告，不把导航行号冒充扫描器输出。
- R10/R12的旧候选表取到了同名软件依赖，现已改为真正的api资产证据。R01–R03固定具体资源ID与版本，避免多版本混淆。
- AI建议是同类风险共享的核验步骤，不能当作已核准许可。建议具体性、顺序和适用性待真人评审；本轮不调整模型、不重写建议。
- API名称/SDK接口出现在示例、类型导入或兼容性注释中，不自动证明真实请求、实际供应商、付费关系或授权。每条应结合上下文审阅。
- 本轮从实际JSON附件抽取记录并核对接口元数据SHA。旧smolagents内部快照与附件有集合排序、工具顺序和report_links差别，相关资源/风险/AI条目一致；本表绑定附件SHA，不把内部快照序列化当作附件字节。
- 历史报告早于本轮代码HEAD `5ad0073`，此表用于人工内容复核，不代替固定验收代码的Windows回执或P0冻结。

## 报告来源

| 项目 | 任务ID | 历史终态 | 本轮读取JSON附件SHA-256 |
|---|---|---|---|
| openai-python | `scn_abd52930-829d-438a-a36d-79717dee3990` | completed | `ef0ad44027da9c57e689ec749f13ca90fb26e59ce364e6364123cf410613aa98` |
| smolagents | `scn_5cba3784-afe2-42e1-b2f0-5bd6230f8587` | partial | `37cb487045c326b2663cf3016f13f487da8fc15f603b0e1661cf4f4686c893a7` |
| litellm | `scn_34e7f56e-b4a1-4291-ae97-7b06f6c612d8` | partial | `e92e13ee42fe964819a3cb31b891dcb5c2ce97fe135b2c26a2d4ea008cb1d860` |

## R01 · 软件 · pydantic

原文件：[查看固定版本与上下文](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/pyproject.toml#L69)。资源版本：`未固定/约束声明`。

```text
66:     "pytest-xdist>=3.6.1",
67:     "griffe>=1",
68: ]
69: pydantic-v1 = ["pydantic>=1.10.26,<2"]
70: pydantic-v2 = ["pydantic>=2,<3"]
71: # Isolated build requirements are exported with hashes by scripts/build.
72: build = [
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`cmp_03e95893-2932-52b3-8d9b-84c43d27ccd1`
- Risk：`rsk_77ea981d-9516-5794-9b3c-665539c0c788`
- 主证据：`evd_3942961d-ac62-5a1a-ae71-b23920566b87`；`pyproject.toml:dependency-groups.pydantic-v1[0]`；SHA `a3190a42805422ecebc40fd522d2638a8c17c7149e79051451e8e24bb4a03258`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_05f6da8c-62ea-5dcc-bcb7-9a54cc60e991`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，确认是否允许当前用途。
  3. 查该pypi资源的官方许可声明原文，明确其许可类型与使用范围。
- AI所引Evidence：`evd_3942961d-ac62-5a1a-ae71-b23920566b87`, `evd_d0d33b22-fd6a-5a1f-99ac-b9d3cfe94d16`, `evd_e73800f7-83c6-5e6a-8ecc-5a9a5ec52f0b`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R02 · 软件 · pycparser

原文件：[查看固定版本与上下文](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/uv.lock#L1880)。资源版本：`2.23`。

```text
1877: ]
1878:
1879: [[package]]
1880: name = "pycparser"
1881: version = "2.23"
1882: source = { registry = "https://pypi.org/simple" }
1883: sdist = { url = "https://files.pythonhosted.org/packages/fe/cf/d2d3b9f5699fb1e4615c8e32ff220203e43b248e1dfcc6736ad9057731ca/pycparser-2.23.tar.gz", hash = "sha256:78816d4f24add8f10a06d6f05b4d424ad9e96cfebf68a4ddc99c65c0720d00c2", size = 173734, upload-time = "2025-09-09T13:23:47.91Z" }
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`cmp_05c41686-f464-5cb5-a67d-8c22030b00b0`
- Risk：`rsk_fa0f182f-6022-59dd-9c0e-4640c1e74ee7`
- 主证据：`evd_12ab606c-32c7-5a24-9ffd-d9ffafff742f`；`uv.lock`；SHA `e70d75cd22a5411a38517060cce262d3ed7e07c353865d0c363c2235dec80a15`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_b3254298-1922-5199-80e6-8e2ae17c8e96`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，确认是否允许当前用途。
  3. 查该pypi资源的官方许可声明原文，明确其许可类型与使用范围。
- AI所引Evidence：`evd_12ab606c-32c7-5a24-9ffd-d9ffafff742f`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R03 · 软件 · anyio

原文件：[查看固定版本与上下文](https://github.com/openai/openai-python/blob/be928151372e4b62adb4a1571cda52ad759b38be/uv.lock#L215)。资源版本：`4.12.1`。

```text
212: ]
213:
214: [[package]]
215: name = "anyio"
216: version = "4.12.1"
217: source = { registry = "https://pypi.org/simple" }
218: dependencies = [
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`cmp_10924453-22fc-5c14-9918-626935fc135e`
- Risk：`rsk_ad0acba4-24af-5958-b3b0-f28ee6cbb75e`
- 主证据：`evd_bd29b0ae-8bf8-5af0-9897-a3c843d02abd`；`uv.lock`；SHA `e70d75cd22a5411a38517060cce262d3ed7e07c353865d0c363c2235dec80a15`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_449f6651-ab27-5ddd-82fd-e0c72b7dbc16`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，确认是否允许当前用途。
  3. 查该pypi资源的官方许可声明原文，明确其许可类型与使用范围。
- AI所引Evidence：`evd_bd29b0ae-8bf8-5af0-9897-a3c843d02abd`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R04 · 模型 · Qwen/Qwen3-Next-80B-A3B-Thinking

原文件：[查看固定版本与上下文](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/docs/source/en/examples/multiagents.md#L39)。资源版本：`未固定/约束声明`。

```text
36: login()
37: ```
38:
39: ⚡️ Our agent will be powered by [Qwen/Qwen3-Next-80B-A3B-Thinking](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking) using `InferenceClientModel` class that uses HF's Inference API: the Inference API allows to quickly and easily run any OS model.
40:
41: > [!TIP]
42: > Inference Providers give access to hundreds of models, powered by serverless inference partners. A list of supported providers can be found [here](https://huggingface.co/docs/inference-providers/index).
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_ed486083-ffcb-5cbd-9fce-1d25dfcc7441`
- Risk：`rsk_d4f369b3-8175-5e32-ad00-f2f6da4b108c`
- 主证据：`evd_d2bb69c9-a420-5070-9758-3b676f01a850`；`docs/source/en/examples/multiagents.md`；SHA `fe70642c6a64e55e32344edb12955abc09c5fab55857fb4986b3369a040ef8f7`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_677cb5e8-84bd-5ea9-8f5f-6883f941bff2`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可文件、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，判断是否存在冲突或限制。
  3. 查该模型的原始许可文件，确认其是否包含使用条款与分发限制。
- AI所引Evidence：`evd_28dbf37a-5ed9-54c9-b588-826aa62eb334`, `evd_34fcd494-6ad0-538c-b5b1-7cf7f81b00eb`, `evd_494394e9-f47d-5325-9cfb-e373789ad459`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R05 · 模型 · black-forest-labs/FLUX.1-dev

原文件：[查看固定版本与上下文](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/docs/source/en/tutorials/tools.md#L258)。资源版本：`未固定/约束声明`。

```text
255:
256: You only need to provide the id of the Space on the Hub, its name, and a description that will help your agent understand what the tool does. Under the hood, this will use [`gradio-client`](https://pypi.org/project/gradio-client/) library to call the Space.
257:
258: For instance, let's import the [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) Space from the Hub and use it to generate an image.
259:
260: ```python
261: image_generation_tool = Tool.from_space(
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_ed8be940-6081-5fc8-a80d-955f509ed4a7`
- Risk：`rsk_dc8f4b94-49a4-5dbb-ae77-a982ff65f952`
- 主证据：`evd_bbe71a36-1c7e-5bbb-82ce-06207b95c2a9`；`docs/source/en/tutorials/tools.md`；SHA `57b9f1deeb7448f456f74cbbd6401241313729f7741cbe24c6dc298cfb47de02`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_94c8da46-a19a-500d-9580-26a793db0fcd`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可文件、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，判断是否存在冲突或限制。
  3. 查该模型的原始许可文件，确认其是否包含使用条款与分发限制。
- AI所引Evidence：`evd_2b5652b0-73ed-5c09-9829-33c2bba50fc2`, `evd_bbe71a36-1c7e-5bbb-82ce-06207b95c2a9`, `evd_f2c50281-01ec-50b1-8258-5b7e1da069ec`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R06 · 模型 · intfloat/multilingual-e5-large-instruct

原文件：[查看固定版本与上下文](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/scripts/sync_together_ai_models.py#L138)。资源版本：`未固定/约束声明`。

```text
135:     ),
136:     _rule(
137:         "intfloat/multilingual-e5-large-instruct",
138:         "embedding dims per https://huggingface.co/intfloat/multilingual-e5-large-instruct",
139:         output_vector_size=1024,
140:     ),
141:     _rule(
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_56cd95d3-b5ec-54db-994a-d9b6d6c6d4c4`
- Risk：`rsk_1ab7ccfb-bb8e-5e87-af91-448422fa58c8`
- 主证据：`evd_454337bf-87f6-5a9c-9b56-1e25c52aaf02`；`scripts/sync_together_ai_models.py`；SHA `1ac3017acb5819e088d3645f711d9b87752dd40ef6f5e0753cc3bc11dc738c7f`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_3f5900ae-9a32-550a-9b06-7e69f441cd23`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可文件、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定使用及分发场景对照，判断是否存在冲突或限制。
  3. 查该模型的原始许可文件，确认其是否包含使用条款与分发限制。
- AI所引Evidence：`evd_454337bf-87f6-5a9c-9b56-1e25c52aaf02`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R07 · 数据集 · smolagents/GAIA-annotated

原文件：[查看固定版本与上下文](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/examples/open_deep_research/README.md#L64)。资源版本：`未固定/约束声明`。

```text
61:
62: This process was done manually but could be automatized.
63:
64: After processing, the annotated was uploaded to a [new dataset](https://huggingface.co/datasets/smolagents/GAIA-annotated). You need to request access (granted instantly).
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_d1b55ffc-edff-5b47-80e3-60a3c1020037`
- Risk：`rsk_d510cef2-9491-58da-8207-ad22b8f5133e`
- 主证据：`evd_9ceb6efd-f199-5a07-b65a-9bdc246dfdcb`；`examples/open_deep_research/README.md`；SHA `f66031c51430af60d61e42177b3e48d84c6ae23d483cfee2eb406b084e992732`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_eef72c0d-46ca-570b-9d6c-a31260486985`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟用于训练、推理及分发的场景对照，验证是否允许此类用途。
  3. 查该数据集的原始许可文件，确认其完整文本内容。
- AI所引Evidence：`evd_9ceb6efd-f199-5a07-b65a-9bdc246dfdcb`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R08 · 数据集 · smolagents-benchmark/benchmark-v1

原文件：[查看固定版本与上下文](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/examples/smolagents_benchmark/run.py#L46)。资源版本：`未固定/约束声明`。

```text
43:         type=str,
44:         default="smolagents/benchmark-v1",
45:     )
46:     # The eval dataset is gated, so you must first visit its page to request access: https://huggingface.co/datasets/smolagents-benchmark/benchmark-v1
47:     parser.add_argument(
48:         "--model-type",
49:         type=str,
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_e04b4f3b-b432-57d0-9b68-b6bfdfea6f62`
- Risk：`rsk_30707999-1fd6-5b8c-a151-5b86b95d967a`
- 主证据：`evd_e6019f33-6d11-5a5f-9656-3cb932e7483c`；`examples/smolagents_benchmark/run.py`；SHA `a1db747335affe27b9c28f99c6fda13c614ba047f2ff8a47486ae4339d420da2`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_193e70a4-83fb-5118-b75b-a91ae98408f5`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟用于训练、推理及分发的场景对照，验证是否允许此类用途。
  3. 查该数据集的原始许可文件，确认其完整文本内容。
- AI所引Evidence：`evd_e6019f33-6d11-5a5f-9656-3cb932e7483c`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R09 · 数据集 · m-ric/agents_medium_benchmark_2

原文件：[查看固定版本与上下文](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/README.md#L258)。资源版本：`未固定/约束声明`。

```text
255:
256: ## How strong are open models for agentic workflows?
257:
258: We've created [`CodeAgent`](https://huggingface.co/docs/smolagents/reference/agents#smolagents.CodeAgent) instances with some leading models, and compared them on [this benchmark](https://huggingface.co/datasets/m-ric/agents_medium_benchmark_2) that gathers questions from a few different benchmarks to propose a varied blend of challenges.
259:
260: [Find the benchmarking code here](https://github.com/huggingface/smolagents/blob/main/examples/smolagents_benchmark/run.py) for more detail on the agentic setup used, and see a comparison of using LLMs code agents compared to vanilla (spoilers: code agents works better).
261:
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_e3797863-c272-5d73-b32c-9666a9af0b72`
- Risk：`rsk_d36e29fd-5f08-5c10-bf9c-130d6ab3dba1`
- 主证据：`evd_71294d6a-1166-5214-9913-054bf1c8b0d1`；`README.md`；SHA `131628d2669b4ee983c715002b57ea4b375b62c8502f6354b8d9fdf3fbc39f8d`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_b51637b7-6030-5ba4-be49-28e145a788ff`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录，作为验收依据。
  2. 将许可原文与拟用于训练、推理及分发的场景对照，验证是否允许此类用途。
  3. 查该数据集的原始许可文件，确认其完整文本内容。
- AI所引Evidence：`evd_71294d6a-1166-5214-9913-054bf1c8b0d1`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R10 · API · anthropic

原文件：[查看固定版本与上下文](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/anthropic_interface/readme.md#L49)。资源版本：`未固定/约束声明`。

```text
46: #### Streaming example
47: ```python showLineNumbers title="Example using LiteLLM Python SDK"
48: import litellm
49: response = await litellm.anthropic.messages.acreate(
50:     messages=[{"role": "user", "content": "Hello, can you tell me a short joke?"}],
51:     api_key=api_key,
52:     model="anthropic/claude-3-haiku-20240307",
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_0401bc9c-79b4-5952-b81c-5e767930f282`
- Risk：`rsk_53f7192d-9ba5-5f2f-9731-66107755e10c`
- 主证据：`evd_2ce6aae7-02b1-5d08-92e3-23448cafa9dc`；`litellm/anthropic_interface/readme.md`；SHA `649aa8e07ccf2154fa5f6a41884f37cfd7bb1f1c569962b7d6dc056db8440cf7`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_8050ee24-2ac7-536a-bf5f-3fb927c3c4f6`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定的使用及分发场景进行对照，确认是否符合授权范围。
  3. 查该API的原始许可条款文档，明确其使用范围与限制条件。
- AI所引Evidence：`evd_2ce6aae7-02b1-5d08-92e3-23448cafa9dc`, `evd_46e3cec7-aa0e-5125-b763-7711fe260a92`, `evd_9064e7e9-6edf-5d56-ab2c-9fd5d5b3f40c`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R11 · API · google

原文件：[查看固定版本与上下文](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/google_genai/Readme.md#L27)。资源版本：`未固定/约束声明`。

```text
24:
25: ```python
26: from litellm.google_genai import generate_content, agenerate_content
27: from google.genai.types import ContentDict, PartDict
28:
29: # Synchronous usage
30: contents = ContentDict(
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_bc80712e-679f-5b40-9b70-27563095ba22`
- Risk：`rsk_d8546fd1-5271-5531-ae1b-d8494023bcea`
- 主证据：`evd_3799c037-95ec-5ca2-bfb9-df3776696848`；`litellm/google_genai/Readme.md`；SHA `05eb67a90e2c711d42d1d6e17a380e41f6bd67fcf51f6e08900166c72123333a`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_827e981a-9e7f-5e23-836b-d10f57866321`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定的使用及分发场景进行对照，确认是否符合授权范围。
  3. 查该API的原始许可条款文档，明确其使用范围与限制条件。
- AI所引Evidence：`evd_3799c037-95ec-5ca2-bfb9-df3776696848`, `evd_417e942a-9b11-5a17-89c8-addabee6c106`, `evd_a73114b4-72fb-5156-b74e-61fabfa421b6`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## R12 · API · openai

原文件：[查看固定版本与上下文](https://github.com/BerriAI/litellm/blob/168a0055a244acdcf97c330c52e085ab40b1424c/litellm/router.py#L974)。资源版本：`未固定/约束声明`。

```text
971:         self.fail_calls: defaultdict = defaultdict(int)  # dict to store fail_calls made to each model
972:         self.success_calls: defaultdict = defaultdict(int)  # dict to store success_calls  made to each model
973:
974:         # make Router.chat.completions.create compatible for openai.chat.completions.create
975:         default_litellm_params = default_litellm_params or {}
976:         self.chat = litellm.Chat(params=default_litellm_params, router_obj=self)
977:
```

第一阶段（本人填写）：对象/情境【待填】；依据【待填】；引用/许可/授权及理由【待填】；不确定事项【待填】。

<details>
<summary>第二阶段：完成独立判断后展开系统记录</summary>

- Resource：`ast_eff857a0-0163-55be-94d5-d5658cab8a39`
- Risk：`rsk_ef3079cc-748d-5034-a312-e742e2787f28`
- 主证据：`evd_16c7a251-ef25-5c6b-9fb1-dde7dd530fab`；`litellm/router.py`；SHA `3ad43f8503791ea9bee2db8d2953c0f13edaab65ab0aab6f8372ffc6aa9fea57`
- 系统许可表达式：`NOASSERTION`；风险：`review_required` / `info`；规则：`license-evidence-gate@2026.09.1`。
- AI：`rem_c75efd66-f41a-58f4-be6e-f2e456939e6a`；状态 `pending`；摘要：【同类风险AI核验建议，未逐项确认许可】现有证据尚未完成许可核验，不能据此判定授权有效或无效。
- 原始AI步骤（保持原顺序）：
  1. 保留许可原文、使用场景说明及对照记录作为验收依据。
  2. 将许可原文与拟定的使用及分发场景进行对照，确认是否符合授权范围。
  3. 查该API的原始许可条款文档，明确其使用范围与限制条件。
- AI所引Evidence：`evd_16c7a251-ef25-5c6b-9fb1-dde7dd530fab`, `evd_670fc8a0-4d04-596a-bc02-145ce24551b8`, `evd_7fa652fc-d752-50e7-9261-955dbf0ed1c4`

第二阶段（本人填写）：识别【待填】；证据【待填】；风险【待填】；AI适用性及理由【待填】。

</details>

## 双方提交后的汇总（暂不填写结论）

负责人先分别保存双方原答案，再记录分歧、引用依据、是否阻断及复测结果；不覆盖原判断。收到回执前，不勾选通过，不计算准确率。

| 记录 | 负责人原答案 | cz原答案 | 分歧及依据 | 处理/复验结论 |
|---|---|---|---|---|
| R01 | 待提交 | 待提交 | 待比对 | 未签收 |
| R02 | 待提交 | 待提交 | 待比对 | 未签收 |
| R03 | 待提交 | 待提交 | 待比对 | 未签收 |
| R04 | 待提交 | 待提交 | 待比对 | 未签收 |
| R05 | 待提交 | 待提交 | 待比对 | 未签收 |
| R06 | 待提交 | 待提交 | 待比对 | 未签收 |
| R07 | 待提交 | 待提交 | 待比对 | 未签收 |
| R08 | 待提交 | 待提交 | 待比对 | 未签收 |
| R09 | 待提交 | 待提交 | 待比对 | 未签收 |
| R10 | 待提交 | 待提交 | 待比对 | 未签收 |
| R11 | 待提交 | 待提交 | 待比对 | 未签收 |
| R12 | 待提交 | 待提交 | 待比对 | 未签收 |
