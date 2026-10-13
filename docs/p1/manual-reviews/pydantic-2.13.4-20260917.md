# Pydantic 2.13.4：人工材料查阅记录

> 范围受限的文档记录，不是 OpenGuard 正式 Evidence、Assessment 或 Obligation。
> 已记录实际人工查阅；没有作出“完整许可适用性已核验”或“义务已履行”的结论。

## 1. 记录对象和参与者

- 项目：OpenGuard（`mumingce-star/OpenGuard`）。
- 项目材料基线：`ac6753fd48467eb39d7f4606f1e54e6931d2e386`。
- 对象：项目声明的 `pydantic==2.13.4`，不包括全部传递依赖。
- 人工查阅者：`mumingce`，由用户自报；不是经过身份系统认证的签名。
- 记录日期：2026-09-17。
- 本地材料读取时间：`2026-09-17T08:48:44Z`，来自用户提供的终端输出；不是最终签署时间。
- 整理助手：ChatGPT（GPT-6 Astra Pro），负责定位材料、解释与编排，不代替人工确认。
- 记录依据：用户在本次对话提供的文字、终端输出和 PyPI 来源信息截图。截图及聊天原件没有随本记录提交，不能声称读者能在仓库完整重放该查阅过程。

## 2. 人工实际提供的查阅结果

### 2.1 项目依赖与代码使用

用户确认的依赖版本：`2.13.4`。

终端显示 `backend/pyproject.toml` 中声明：

```toml
"pydantic==2.13.4",
```

用户提供的 `backend/app/domain/models.py` 导入行：

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
```

用户终端提供的完整文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `backend/pyproject.toml` | `941e9f9135d63c940fd13595ec1f978fbbe9d5ba6e70595f514ce925fcba7aa3` |
| `backend/app/domain/models.py` | `f9df66e9afa0b31bdccbe510bfe6d39208278c27dc23df7db8a3a5e5186595dd` |

这些材料支持“该基线声明这个固定依赖，且代码中存在实际导入”。它们不证明某台运行机器安装的版本或包字节。

### 2.2 发布来源页面

用户提供了 PyPI `Source repository` 区域截图，图中可读到：

- Permalink：`pydantic/pydantic@cf67d4b3193c3fe43ede18612ed62785eee11382`。
- Branch / Tag：`refs/tags/v2.13.4`。
- Owner：`https://github.com/pydantic`。
- Access：`public`。

这记录的是页面展示的来源关联。未下载发布制品，未独立验证发布证明或数字签名，未证明本机安装包与该提交逐字节对应。

### 2.3 许可证名称和版权行

用户确认许可证名称为 `MIT`，并提供如下版权行：

```text
Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors.
```

这里只记录上游文件的署名内容，不构成对权利归属的独立调查。

### 2.4 声明保留条件

用户实际提供的原文是以下首行：

```text
The above copyright notice and this permission notice shall be included in all
```

用户没有单独提供下一行，也未单独给出对完整适用范围的解释。不得把整理助手的补充视为用户已经阅读、理解并签署了完整条件。

## 3. 整理助手依据固定原文补充的说明

在同一固定提交的 `LICENSE` 中，上述首行紧接着：

```text
copies or substantial portions of the Software.
```

完整条件的中文说明：软件的所有副本或实质部分中，应包含前述版权声明和许可声明。

本节是 AI 依据来源的转录和解释，不是新增人工核验结论。完整条件范围尚未取得查阅者单独确认；也没有检查 OpenGuard 的实际交付物是否满足该条件。

## 4. 本次结论与未检查事项

本次已经留下真实人工查阅证据：固定依赖声明、代码导入、PyPI 来源区域截图、许可证名称、版权行及条件首行。不能把这些材料概括为“Pydantic 的所有许可与交付条件已核验通过”。

尚未检查或未取得单独确认：

- 查阅者对完整声明保留条件及其范围的最终确认。
- 实际安装的 wheel/sdist、生产容器或交付包字节。
- 包内文件及第三方内容的完整许可适用范围；`pydantic-core` 等传递依赖不在本次核验范围。
- 最终发布物中的版权和许可声明是否已保留。
- 发布证明的密码学验证、独立二次人工复核及完整权属调查。
- 对某次实际 ScanRun / 资源实例的正式证据绑定。本记录没有编造 scan_id、resource_id 或 evidence_id。

## 5. 给前端与后端的使用边界

本记录可以作为真实材料查阅的文档和后续核验输入，不能直接导入为 `verified` Evidence，不能直接修改旧 ScanRun、Formal Assessment、Obligation 或 Report，也不等于已实现人工核验提交 API。

F04 可以继续使用现有固定 Assessment、Task 和明确标注的合成联调样例开发。将本记录接纳成新正式事实并生成新评估，需要单独批准、有版本绑定的接纳流程。

Task `done` 不等于 Obligation 已履行；材料查阅不等于整体项目合规。不得把本记录计作真实扫描性能、Bench Gold 或法律保证。

## 6. 可复查来源

1. [OpenGuard 固定基线的依赖声明](https://github.com/mumingce-star/OpenGuard/blob/ac6753fd48467eb39d7f4606f1e54e6931d2e386/backend/pyproject.toml)。
2. [OpenGuard 固定基线的实际导入](https://github.com/mumingce-star/OpenGuard/blob/ac6753fd48467eb39d7f4606f1e54e6931d2e386/backend/app/domain/models.py)。
3. [Pydantic 2.13.4 发布文件页](https://pypi.org/project/pydantic/2.13.4/#files)：本次来源关联来自用户截图，不把页面地址当作不可变制品摘要。
4. [固定源码提交中的 LICENSE](https://github.com/pydantic/pydantic/blob/cf67d4b3193c3fe43ede18612ed62785eee11382/LICENSE)。
5. [OpenGuard 当前基线的冻结契约](https://github.com/mumingce-star/OpenGuard/blob/ac6753fd48467eb39d7f4606f1e54e6931d2e386/docs/spec/p1-workspace-contract.md)：新证据接纳另行批准，用户备注不是 Evidence。

记录修订应明确新增了哪项实际查阅或核验，不应将后来补充倒填成先前已经确认。
