import unittest


class GuiFontPolicyTests(unittest.TestCase):
    def test_choose_safe_fixed_font_family_falls_back_from_fixedsys(self) -> None:
        from gui import choose_safe_fixed_font_family

        family = choose_safe_fixed_font_family(
            "Fixedsys",
            ["Fixedsys", "Consolas", "Courier New"],
        )

        self.assertEqual(family, "Consolas")

    def test_choose_safe_fixed_font_family_keeps_safe_existing_choice(self) -> None:
        from gui import choose_safe_fixed_font_family

        family = choose_safe_fixed_font_family(
            "Courier New",
            ["Fixedsys", "Courier New", "Consolas"],
        )

        self.assertEqual(family, "Courier New")


if __name__ == "__main__":
    unittest.main()
