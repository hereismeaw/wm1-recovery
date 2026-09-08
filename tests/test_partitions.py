import struct
import unittest

from walkman_recovery.bootimg import pack_cpio, unpack_cpio
from walkman_recovery.partitions import contents_header_kind, parse_mbr_ebr


def _mbr(*entries: tuple[int, int, int]) -> bytes:
    sector = bytearray(512)
    sector[510:512] = b"\x55\xaa"
    for i, (typ, lba, count) in enumerate(entries):
        struct.pack_into("<B", sector, 446 + i * 16 + 4, typ)
        struct.pack_into("<II", sector, 446 + i * 16 + 8, lba, count)
    return bytes(sector)


class PartitionTests(unittest.TestCase):
    def test_extended_chain(self):
        data = bytearray(10 * 512)
        data[0:512] = _mbr((5, 1, 8), (0x83, 2, 2))
        data[512:1024] = _mbr((0x83, 1, 1), (5, 3, 1))
        data[4 * 512 : 5 * 512] = _mbr((0x0C, 1, 2))
        parts = parse_mbr_ebr(bytes(data))
        offsets = [p.offset for p in parts]
        self.assertIn(2 * 512, offsets)
        self.assertTrue(any(p.type == 0x0C for p in parts))

    def test_contents_header_kinds(self):
        fat = bytearray(512)
        fat[0] = 0xEB
        fat[0x52:0x57] = b"FAT32"
        fat[510:512] = b"\x55\xaa"
        self.assertEqual(contents_header_kind(bytes(fat)), "fat32")
        self.assertEqual(contents_header_kind(_mbr((0x0C, 8192, 100), (0x83, 100, 100))), "mbr")
        self.assertEqual(contents_header_kind(bytes(512)), "empty")

    def test_cpio_round_trip(self):
        records = [
            ([0, 0o100644, 0, 0, 0, 0, 4, 0, 0, 0, 0, 6, 0], b"hi\0", b"abcd"),
            ([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 11, 0], b"TRAILER!!!\0", b""),
        ]
        packed = pack_cpio(records)
        back = unpack_cpio(packed)
        self.assertEqual(back[0][1], b"hi\0")
        self.assertEqual(back[0][2], b"abcd")
        self.assertEqual(back[1][1], b"TRAILER!!!\0")
