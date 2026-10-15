"""Comprobaciones mínimas de la integración nativa de Windows."""

import ctypes
import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "Solo aplica en Windows")
class WindowsBackendTests(unittest.TestCase):
    def test_key_codes_and_sendinput_layout(self):
        from pescaauto import platform_windows as windows

        self.assertEqual(windows.key_code("1"), 0x31)
        self.assertEqual(windows.key_code("F8"), 0x77)
        self.assertEqual(windows.key_code("F9"), 0x78)
        self.assertEqual(ctypes.sizeof(windows.INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


if __name__ == "__main__":
    unittest.main()
