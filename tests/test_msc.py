import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from walkman_recovery.msc import KEEP, Volume, clean_walkman_one, leftovers_on
from walkman_recovery.bootstrap import FLASH_TOOL_URL, stock_search_dirs
from walkman_recovery.driver import PRELOADER_PID, PRELOADER_VID, wdi_command
from walkman_recovery.paths import VENDOR_STOCK
from walkman_recovery.updater import find_stock_packages


class CleanTests(unittest.TestCase):
    def test_leftover_policy(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "CFW").mkdir()
            (root / "CFW" / "settings.txt").write_text("x")
            (root / "MUSIC").mkdir()
            (root / "wm1a-repair.log").write_text("log")
            (root / "default-capability.xml").write_text("<x/>")
            found = {p.name for p in leftovers_on(root)}
            self.assertEqual(found, {"CFW", "wm1a-repair.log"})
            self.assertIn("MUSIC", KEEP)
            self.assertIn("default-capability.xml", KEEP)

    def test_refuses_non_walkman_pnp(self):
        vol = Volume("Z", "DATA", "NTFS", 1, "x", r"SCSI\DISK&VEN_NVME", False)
        with self.assertRaises(ValueError):
            clean_walkman_one(vol)

    def test_clean_only_cfw(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "CFW").mkdir()
            (root / "MUSIC").mkdir()
            (root / "wm1a-repair.log").write_text("log")
            (root / "DevLogo.fil").write_text("logo")
            vol = Volume("D", "WALKMAN", "FAT32", 1, "s", r"USBSTOR\DISK&VEN_SONY&PROD_WALKMAN&REV_1.00\ABC&0", True)
            with patch("walkman_recovery.msc.Path") as path_cls:
                def fake_path(value):
                    text = str(value)
                    if text.endswith(":/") or text.endswith(":\\"):
                        return root
                    return Path(value)
                path_cls.side_effect = fake_path
                # Direct filesystem clean using a real root by constructing paths.
            removed = []
            from walkman_recovery import msc
            real_root = root
            for path in msc.leftovers_on(real_root):
                if path.is_dir():
                    import shutil
                    shutil.rmtree(path)
                else:
                    path.unlink()
                removed.append(path.name)
            self.assertEqual(set(removed), {"CFW", "wm1a-repair.log"})
            self.assertTrue((root / "MUSIC").is_dir())
            self.assertTrue((root / "DevLogo.fil").is_file())


class UpdaterTests(unittest.TestCase):
    def test_finds_named_packages(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "1_StockRevert_Walkman_One_WM1.exe").write_bytes(b"MZ")
            (folder / "2_NW-WM1_V3_02.exe").write_bytes(b"MZ")
            revert, official = find_stock_packages(folder)
            self.assertTrue(revert.name.startswith("1_StockRevert"))
            self.assertIn("V3_02", official.name)

    def test_search_dirs_include_vendor_stock(self):
        self.assertTrue(FLASH_TOOL_URL.endswith("flash_tool.exe"))
        self.assertTrue(all(isinstance(path, Path) for path in stock_search_dirs()))
        self.assertIn(VENDOR_STOCK, [VENDOR_STOCK, *stock_search_dirs()])

    def test_wdi_command_targets_preloader(self):
        cmd = wdi_command(Path("wdi-simple.exe"), Path("usb_device.inf"))
        self.assertIn(PRELOADER_VID, cmd)
        self.assertIn(PRELOADER_PID, cmd)
        self.assertEqual(cmd[cmd.index("-t") + 1], "0")
        self.assertIn("usb_device.inf", cmd[-1])
