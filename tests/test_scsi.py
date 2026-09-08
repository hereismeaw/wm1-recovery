import ctypes
import struct
import unittest

from walkman_recovery.scsi import (
    COMMANDS,
    READ_OPCODES,
    SPT,
    descriptor,
    is_walkman,
    parse_devinfo,
    sense_decode,
)


class ScsiTests(unittest.TestCase):
    def test_windows_abi(self):
        self.assertEqual(ctypes.sizeof(SPT), 56 if ctypes.sizeof(ctypes.c_void_p) == 8 else 44)
        self.assertEqual(SPT.DataTransferLength.offset, 12)
        self.assertEqual(SPT.Cdb.offset, 36 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_walkman_identity_is_not_serial_locked(self):
        raw = bytearray(100)
        struct.pack_into("<IIIII", raw, 12, 36, 41, 49, 54, 7)
        raw[36:41] = b"SONY\0"
        raw[41:49] = b"WALKMAN\0"
        raw[49:54] = b"1.00\0"
        raw[54:70] = b"10453075026180\0"
        info = descriptor(raw)
        self.assertTrue(is_walkman(info))
        self.assertTrue(is_walkman({**info, "serial": "anything"}))
        self.assertFalse(is_walkman({**info, "vendor": "OTHER"}))
        self.assertFalse(is_walkman({**info, "product": "SSD"}))
        self.assertFalse(is_walkman({**info, "bus": 3}))
        struct.pack_into("<I", raw, 12, 999)
        with self.assertRaises(ValueError):
            descriptor(raw)

    def test_sense_formats(self):
        fixed = bytearray(18)
        fixed[0], fixed[2], fixed[12] = 0x70, 2, 0x3A
        result = sense_decode(fixed)
        self.assertEqual((result["key"], result["asc"], result["ascq"]), (2, 0x3A, 0))
        result = sense_decode(bytes.fromhex("72 02 04 01 00 00 00 00"))
        self.assertEqual(result["meaning"], "Device becoming ready")
        self.assertIsNone(sense_decode(bytes(32)))

    def test_read_commands_only(self):
        for cdb, size in COMMANDS.values():
            self.assertIn(cdb[0], READ_OPCODES)
            if cdb[0] == 0xDD:
                self.assertEqual(cdb[7], 0xBC)
                self.assertEqual(cdb[10], 0x23)

    def test_devinfo_stock_wm1a(self):
        raw = bytes.fromhex(
            "444556494e464f800000000000000000"
            "534f4e59202020204e572d574d314100"
            "0000000000000000332e303230302020"
            "31323847353032363138390000000000"
        ) + bytes(64)
        info = parse_devinfo(raw)
        self.assertEqual(info["model"], "NW-WM1A")
        self.assertEqual(info["firmware"], "3.0200")
        self.assertEqual(info["storage"], "128G")
        self.assertEqual(info["serial"], "5026189")
