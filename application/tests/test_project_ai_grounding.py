import json
import unittest

from app.ai.project import context, validate


def payload(*, restricted=False):
    return json.dumps({
        "schema_version": "openguard-project-qa/v6",
        "assessment_id": "asm-test",
        "state_digest": "state-test",
        "formal_state": {
            "dimensions": [{
                "id": "commercial",
                "status": "restricted" if restricted else "unknown",
                "conclusion": "当前用途存在限制" if restricted else "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": ["明确限制"] if restricted else [],
            }],
            "coverage": [],
            "usage": {},
            "summary": "已有扫描事实，但仍需核验。",
            "review_groups": [],
        },
        "review_groups": [],
        "selected_resources": [],
        "evidence": [],
    }, ensure_ascii=False)


def response(answer):
    return json.dumps({
        "assessment_id": "asm-test",
        "state_digest": "state-test",
        "answer": answer,
        "evidence_ids": [],
    }, ensure_ascii=False)


class ProjectAIGroundingTests(unittest.TestCase):
    def test_unknown_must_not_be_rewritten_as_prohibition(self):
        safe = "当前证据不足，尚无法确认商用或分发条件；这不代表禁止商用或分发。下一步应核对许可原文及适用范围。"
        self.assertEqual(validate(response(safe), payload())["answer"], safe)
        safe2 = "当前仍需核验证据，这不等于禁止商业使用，也并非禁止分发。"
        self.assertEqual(validate(response(safe2), payload())["answer"], safe2)
        with self.assertRaisesRegex(ValueError, "project_unknown_is_not_prohibition"):
            validate(response("整体许可状态尚未完成独立核验，因此不具备可商用或分发的法律基础。"), payload())

    def test_restricted_state_may_describe_recorded_restriction(self):
        answer = "正式评估记录了明确限制，因此当前交付用途存在限制；仍需按照记录的条件继续核验。"
        self.assertEqual(validate(response(answer), payload(restricted=True))["answer"], answer)

    def test_mixed_restricted_does_not_prohibit_unknown_dimensions(self):
        mixed = json.loads(payload())
        mixed["formal_state"]["dimensions"] = [
            {
                "id": "commercial",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
            },
            {
                "id": "closed_distribution",
                "status": "restricted",
                "conclusion": "当前用途存在限制",
                "conditions": [],
                "restrictions": ["当前闭源交付方案存在明确限制"],
            },
            {
                "id": "redistribution",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
            },
            {
                "id": "modification",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
            },
            {
                "id": "network_service",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
            },
            {
                "id": "ai_assets",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
            },
        ]
        mixed_payload = json.dumps(mixed, ensure_ascii=False)

        safe = (
            "闭源交付维度记录了明确限制，因此当前闭源交付方案不能直接执行；"
            "商业使用和公开发布仍为证据不足，需要继续核验。"
        )
        self.assertEqual(
            validate(response(safe), mixed_payload)["answer"],
            safe,
        )

        safe_unknown_answers = (
            "闭源交付维度存在明确限制；商业使用目前不能确认，仍需核验。",
            "闭源交付维度存在明确限制；在线服务是否可行目前不能判断。",
            "闭源交付维度存在明确限制；模型授权条件目前不能确定。",
            "闭源交付维度存在明确限制；数据集许可状态目前不能核实。",
        )
        for answer in safe_unknown_answers:
            with self.subTest(answer=answer):
                self.assertEqual(
                    validate(response(answer), mixed_payload)["answer"],
                    answer,
                )

        unsafe_answers = (
            "闭源交付维度记录了明确限制；商业使用不能进行。",
            "闭源交付维度记录了明确限制；公开发布不能进行。",
            "闭源交付维度记录了明确限制；该项目不能修改。",
            "闭源交付维度记录了明确限制；不能用于对外在线服务。",
            "闭源交付维度记录了明确限制；这些模型不能使用。",
            "闭源交付维度记录了明确限制；项目整体缺少有效授权依据。",
        )
        for answer in unsafe_answers:
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(
                    ValueError,
                    "project_unknown_is_not_prohibition",
                ):
                    validate(response(answer), mixed_payload)

    def test_version_range_is_not_html_but_html_stays_blocked(self):
        answer = "urllib3版本范围为urllib3<3,>=1.26；这只是声明范围，实际安装版本和对应许可仍待核验。"
        self.assertEqual(validate(response(answer), payload())["answer"], answer)
        with self.assertRaisesRegex(ValueError, "project_unsafe_output"):
            validate(response("当前仍待核验<script>alert(1)</script>，请继续检查。"), payload())


class _ContextAssessment:
    id = "asm-context"

    def __init__(self, summary="已有扫描事实，但关键授权仍需核验。"):
        self.summary = summary

    def model_dump(self, mode="json"):
        return {
            "id": self.id,
            "input_hash": "input-context",
            "summary": self.summary,
            "usage": {"preset": "unknown"},
            "coverage_issues": [],
            "resource_ids": [],
            "resource_evaluations": [],
            "obligations": [],
            "dimensions": [{
                "id": "commercial",
                "title": "商业使用",
                "status": "unknown",
                "conclusion": "证据不足，暂无法判断",
                "conditions": [],
                "restrictions": [],
                "unknowns": [],
                "resource_ids": [],
                "finding_ids": [],
                "evidence_ids": [],
            }],
        }


class _ContextProject:
    name = "requests"
    revision = "revision-context"


class _ContextRun:
    evidence = []
    project = _ContextProject()


class ProjectAIContextBudgetTests(unittest.TestCase):
    def test_single_turn_context_keeps_formal_state_and_one_review_projection(self):
        raw = context(
            _ContextRun(),
            _ContextAssessment(),
            "这个项目现在能不能商用？",
            [],
        )

        self.assertLessEqual(len(raw.encode("utf-8")), 12000)

        data = json.loads(raw)

        self.assertEqual(
            data["formal_state"]["dimensions"][0]["status"],
            "unknown",
        )
        self.assertNotIn("review_groups", data["formal_state"])
        self.assertIn("review_groups", data)
        self.assertEqual(raw.count('"review_groups"'), 1)
        self.assertEqual(data["history"], [])
        self.assertEqual(data["history_included"], 0)

    def test_multiturn_history_is_bounded_and_failed_turns_are_not_promoted(self):
        history = []

        for index in range(6):
            history.append({
                "status": "succeeded",
                "question": f"{index}-" + ("问题" * 1000),
                "answer": f"{index}-" + ("回答" * 1000),
                "evidence_ids": [
                    "evd_a",
                    "evd_b",
                    "evd_c",
                    "evd_d",
                    "evd_extra",
                ],
            })

        history.append({
            "status": "failed",
            "question": "这个失败问题不能成为后续模型事实",
            "answer": "失败回答",
            "evidence_ids": ["evd_failed"],
        })

        raw = context(
            _ContextRun(),
            _ContextAssessment(),
            "根目录Apache-2.0能否自动适用于所有依赖？",
            history,
        )

        self.assertLessEqual(len(raw.encode("utf-8")), 12000)

        data = json.loads(raw)

        self.assertEqual(data["history_total"], 7)
        self.assertEqual(data["history_included"], 2)
        self.assertEqual(len(data["history"]), 2)

        for row in data["history"]:
            self.assertIn("question_excerpt", row)
            self.assertIn("answer_excerpt", row)
            self.assertTrue(row["question_truncated"])
            self.assertTrue(row["answer_truncated"])
            self.assertLessEqual(len(row["evidence_ids"]), 4)
            self.assertNotIn("evd_failed", row["evidence_ids"])

        self.assertNotIn("review_groups", data["formal_state"])
        self.assertEqual(
            data["formal_state"]["dimensions"][0]["conclusion"],
            "证据不足，暂无法判断",
        )

    def test_oversized_formal_state_still_fails_instead_of_being_truncated(self):
        assessment = _ContextAssessment(
            summary="正式评估事实" * 5000,
        )

        with self.assertRaisesRegex(
            ValueError,
            "project_context_limit",
        ):
            context(
                _ContextRun(),
                assessment,
                "请解释当前评估。",
                [],
            )


if __name__ == "__main__":
    unittest.main()
