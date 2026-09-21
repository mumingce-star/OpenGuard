"""No Docker, AI, network, or database operations in these regression tests."""
import copy
import importlib
import unittest

rg = importlib.import_module("app.assessment.review_groups")


def sample():
    gap = next(text for text, code in rg.GAP_CODES.items() if code == "license")
    row = {"resource_id": "cmp_a", "name": "pkg", "version": None, "gaps": [gap]}
    d = {"id": "commercial", "title": "商业使用", "conclusion": "证据不足，暂无法判断",
         "status": "unknown", "conditions": [], "restrictions": [], "resource_ids": ["cmp_a"],
         "unknowns": [f"pkg（版本未确定）：{gap}", rg.USAGE_REASON, "partial范围需检查"]}
    return {"id": "asm_test", "coverage_issues": ["partial范围需检查"],
            "resource_evaluations": [row], "dimensions": [d]}


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.data = sample()

    def test_three_categories(self):
        v = rg.review_view(self.data)
        self.assertEqual([g["code"] for g in v["groups"]], ["usage", "license", "coverage"])
        self.assertEqual(v["dimensions"][0]["raw_count"], 3)

    def test_conservation_and_no_mutation(self):
        before = copy.deepcopy(self.data)
        v = rg.review_view(self.data)
        by_id = {g["id"]: g for g in v["groups"]}
        restored = {}
        for ref in v["dimensions"][0]["groups"]:
            for index, item in zip(ref["unknown_indices"], by_id[ref["group_id"]]["items"]):
                self.assertNotIn(index, restored)
                restored[index] = item["text"]
        self.assertEqual([restored[i] for i in sorted(restored)], before["dimensions"][0]["unknowns"])
        self.assertEqual(self.data, before)

    def test_new_phrase_preserved(self):
        self.data["dimensions"][0]["unknowns"].append("未来新规则：未经识别的原因")
        v = rg.review_view(self.data)
        self.assertEqual(v["groups"][-1]["code"], "other")
        self.assertEqual(v["groups"][-1]["items"][0]["text"], "未来新规则：未经识别的原因")

    def test_duplicate_occurrences_not_erased(self):
        self.data["dimensions"][0]["unknowns"] *= 2
        v = rg.review_view(self.data)
        self.assertEqual(v["dimensions"][0]["raw_count"], 6)
        self.assertEqual(sum(g["raw_count"] for g in v["groups"]), 6)

    def test_identical_dimensions_share_groups(self):
        second = copy.deepcopy(self.data["dimensions"][0])
        second["id"] = "modification"
        self.data["dimensions"].append(second)
        v = rg.review_view(self.data)
        self.assertEqual(len(v["groups"]), 3)
        self.assertTrue(all(len(g["dimension_ids"]) == 2 for g in v["groups"]))

    def test_changed_dimension_not_coalesced(self):
        second = copy.deepcopy(self.data["dimensions"][0])
        second.update(id="modification", unknowns=["完全不同的原因"])
        self.data["dimensions"].append(second)
        v = rg.review_view(self.data)
        self.assertEqual(len(v["groups"]), 4)
        self.assertEqual(v["dimensions"][1]["raw_count"], 1)

    def test_ambiguous_resource_labels_keep_both_ids(self):
        extra = dict(self.data["resource_evaluations"][0], resource_id="cmp_b")
        self.data["resource_evaluations"].append(extra)
        self.data["dimensions"][0]["resource_ids"].append("cmp_b")
        group = next(g for g in rg.review_view(self.data)["groups"] if g["code"] == "license")
        self.assertEqual(group["resource_ids"], ["cmp_a", "cmp_b"])

    def test_unrelated_resource_not_added(self):
        self.data["resource_evaluations"].append(dict(self.data["resource_evaluations"][0], resource_id="cmp_b"))
        group = next(g for g in rg.review_view(self.data)["groups"] if g["code"] == "license")
        self.assertEqual(group["resource_ids"], ["cmp_a"])

    def test_ai_prompt_is_not_an_asset(self):
        self.data["dimensions"][0].update(id="ai_assets", resource_ids=[], unknowns=[rg.AI_REASON])
        v = rg.review_view(self.data)
        self.assertEqual(v["groups"][0]["code"], "ai_review")
        self.assertEqual(v["groups"][0]["resource_ids"], [])

    def test_html_escaped(self):
        self.data["dimensions"][0]["unknowns"].append('<script>alert("x")</script>')
        out = rg.render_grouped_reviews(self.data)
        self.assertNotIn('<script>', out)
        self.assertIn('&lt;script&gt;', out)
        self.assertIn('证据不足，暂无法判断', out)

    def test_no_reason_not_permission(self):
        self.data["dimensions"][0]["unknowns"] = []
        v = rg.review_view(self.data)
        self.assertEqual(v["groups"], [])
        self.assertEqual(self.data["dimensions"][0]["status"], "unknown")

    def test_view_not_persisted_in_model(self):
        before = copy.deepcopy(self.data)
        shown = rg.present_assessment(self.data)
        self.assertFalse(shown["review_view"]["formal"])
        self.assertEqual({k: v for k, v in shown.items() if k != "review_view"}, before)
        self.assertNotIn("review_view", self.data)

    def test_bad_strings_rejected(self):
        self.data["dimensions"][0]["unknowns"] = [None]
        with self.assertRaises(ValueError):
            rg.review_view(self.data)

    def test_duplicate_dimensions_rejected(self):
        self.data["dimensions"].append(copy.deepcopy(self.data["dimensions"][0]))
        with self.assertRaises(ValueError):
            rg.review_view(self.data)

    def test_deterministic(self):
        self.assertEqual(rg.review_view(self.data), rg.review_view(copy.deepcopy(self.data)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
