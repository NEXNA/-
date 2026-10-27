from __future__ import annotations

import unittest


class ControlPanelTest(unittest.TestCase):
    def test_module_imports_without_opening_window(self):
        import control_panel

        self.assertTrue(hasattr(control_panel, "MochaControlPanel"))
        self.assertEqual(control_panel.TASK_NAME, "QQSettingBot")


if __name__ == "__main__":
    unittest.main()
