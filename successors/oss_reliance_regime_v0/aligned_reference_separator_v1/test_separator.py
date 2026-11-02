import unittest
import study as s


def mock(rows, differ=()):
    return {
        u: {
            q["qid"]: ("B" if q["law"] == "A" else "A")
            if u in s.SMALL and q["mode"] in differ
            else q["law"]
            for q in rows
        }
        for u in s.UNITS
    }


class SeparatorTests(unittest.TestCase):
    def test_nonconflict_and_single_manipulation(self):
        rs = s.panel("development", s.VARIANTS)
        self.assertEqual(len(rs), 72)
        for i in range(0, len(rs), 6):
            base = rs[i]["prompt_text"]
            heading = rs[i + 2]["prompt_text"]
            moved = rs[i + 4]["prompt_text"]
            self.assertEqual(
                heading, base.replace("Advisory ribbon (not law)", "Filing note (not law)")
            )
            self.assertCountEqual(base.splitlines(), moved.splitlines())
            self.assertNotEqual(base, moved)
            self.assertEqual(
                rs[i]["qid"].split("/")[-3], base.split("(not law): ")[1].splitlines()[0]
            )
        a = {q["docket"] for q in rs}
        b = {q["docket"] for q in s.panel("confirmation", s.VARIANTS)}
        self.assertFalse(a & b)

    def test_priority_and_no_tuning(self):
        rs = s.panel("development", s.VARIANTS)
        self.assertIsNone(s.evaluate(rs, mock(rs))["chosen"])
        self.assertEqual(s.evaluate(rs, mock(rs, ("heading", "position")))["chosen"], "heading")
        self.assertEqual(s.evaluate(rs, mock(rs, ("position",)))["chosen"], "position")

    def test_unparseable_unstable_or_baseline_drift_is_not_separation(self):
        rs = s.panel("development", s.VARIANTS)
        for bad, mode in (("explanation", "heading"), (None, "heading"), ("bad", "baseline")):
            data = mock(rs, ("heading",))
            q = next(q for q in rs if q["mode"] == mode)
            data[s.SMALL[0]][q["qid"]] = (
                bad if bad is not None else ("B" if data[s.SMALL[0]][q["qid"]] == "A" else "A")
            )
            self.assertIsNone(s.evaluate(rs, data)["chosen"])

    def test_witness_must_be_distinct_from_every_opposite_reference(self):
        rs = s.panel("development", s.VARIANTS)
        data = mock(rs, ("heading",))
        data[s.SMALL[-1]] = data[s.M].copy()
        self.assertIsNone(s.evaluate(rs, data)["chosen"])

    def test_one_family_is_not_a_primary_prediction(self):
        w = s.panel("confirmation", ("baseline", "heading"))
        h = s.panel("confirmation", ("baseline",), True)
        table = s.branches(w, mock(w, ("heading",)), h, mock(h), "heading")
        single = next(v for v in table["branches"].values() if v["references"] == [s.M])
        self.assertTrue(all(not x for x in single["primary"].values()))
        self.assertTrue(all(len(x) == 1 for x in single["descriptive_only"].values()))

    def test_missing_row_cannot_be_an_ordinary_failure(self):
        rs = s.panel("development", s.VARIANTS)
        data = mock(rs)
        data[s.M].pop(rs[0]["qid"])
        with self.assertRaisesRegex(ValueError, "inventory"):
            s.evaluate(rs, data)
