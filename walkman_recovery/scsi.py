"""Windows SCSI pass-through for Sony Walkman USB devices.

Only SONY/WALKMAN USB disks are opened for SCSI. Physical drive numbers are
never used as identity. Commands are a fixed read-only set.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import struct
import time

IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
IOCTL_SCSI_PASS_THROUGH = 0x0004D004
USB_BUS_TYPE = 7


class SPT(C.Structure):
    _fields_ = [
        ("Length", W.USHORT),
        ("ScsiStatus", W.BYTE),
        ("PathId", W.BYTE),
        ("TargetId", W.BYTE),
        ("Lun", W.BYTE),
        ("CdbLength", W.BYTE),
        ("SenseInfoLength", W.BYTE),
        ("DataIn", W.BYTE),
        ("DataTransferLength", W.ULONG),
        ("TimeOutValue", W.ULONG),
        ("DataBufferOffset", C.c_size_t),
        ("SenseInfoOffset", W.ULONG),
        ("Cdb", W.BYTE * 16),
    ]


def sense_decode(raw: bytes) -> dict | None:
    if not raw or not any(raw):
        return None
    code = raw[0] & 0x7F
    if code in (0x70, 0x71) and len(raw) >= 14:
        key, asc, ascq = raw[2] & 15, raw[12], raw[13]
    elif code in (0x72, 0x73) and len(raw) >= 4:
        key, asc, ascq = raw[1] & 15, raw[2], raw[3]
    else:
        return {"raw": raw.hex(), "meaning": "Unrecognized sense format"}
    meaning = {
        (0x3A, 0): "Medium not present / not exposed by firmware",
        (0x04, 1): "Device becoming ready",
        (0x04, 2): "Initialization required",
        (0x20, 0): "Unsupported command",
        (0x24, 0): "Invalid field in command",
        (0x29, 0): "Power-on, reset, or bus reset",
        (0x28, 0): "Medium changed",
    }.get((asc, ascq), "See SCSI sense codes")
    return {"key": key, "asc": asc, "ascq": ascq, "meaning": meaning, "raw": raw.hex()}


def descriptor(raw: bytes) -> dict:
    if len(raw) < 36:
        raise ValueError("Short storage descriptor")

    def string_at(offset: int) -> str:
        if offset == 0:
            return ""
        if offset >= len(raw):
            raise ValueError("Invalid descriptor string offset")
        return raw[offset:].split(b"\0", 1)[0].decode("ascii", "replace").strip()

    vendor, product, revision, serial, bus = struct.unpack_from("<IIIII", raw, 12)
    return {
        "vendor": string_at(vendor),
        "product": string_at(product),
        "revision": string_at(revision),
        "serial": string_at(serial),
        "bus": bus,
    }


def is_walkman(info: dict) -> bool:
    return (
        info.get("vendor", "").upper() == "SONY"
        and "WALKMAN" in info.get("product", "").upper()
        and info.get("bus") == USB_BUS_TYPE
    )


def dnk(sub: int, size: int) -> bytes:
    cdb = bytearray(12)
    cdb[0], cdb[7], cdb[10], cdb[11] = 0xDD, 0xBC, 0x23, sub
    cdb[8:10] = size.to_bytes(2, "big")
    return bytes(cdb)


COMMANDS = {
    "inquiry": (bytes.fromhex("12 00 00 00 60 00"), 96),
    "ready": (bytes(6), 0),
    "capacity10": (bytes.fromhex("25 00 00 00 00 00 00 00 00 00"), 8),
    "model_id": (dnk(9, 4), 4),
    "storage_gb": (dnk(4, 4), 4),
    "product_id": (dnk(6, 12), 12),
    "capacity16": (bytes.fromhex("9e 10 00 00 00 00 00 00 00 00 00 00 00 20 00 00"), 32),
    "service_devinfo": (bytes.fromhex("fc 00 20 64 62 6d 6e 00 80 00 00 00"), 128),
}

READ_OPCODES = {0x00, 0x12, 0x25, 0x9E, 0xDD, 0xFC}

MODEL_IDS = {
    0x20000007: "NW-WM1A",
    0x21000008: "NW-WM1Z",
}


def parse_devinfo(data: bytes) -> dict:
    if not data.startswith(b"DEVINFO"):
        return {"raw": data[:64].hex()}

    def field(offset: int, size: int = 16) -> str:
        return data[offset:offset + size].split(b"\0", 1)[0].decode("ascii", "replace").strip()

    blob = field(48, 24)
    storage, serial = blob, ""
    if blob.startswith("128G") or blob.startswith("256G"):
        storage, serial = blob[:4], blob[4:]
    return {
        "vendor": field(16, 8),
        "model": field(24, 16),
        "firmware": field(40, 8),
        "storage": storage,
        "serial": serial,
    }


class WindowsSCSI:
    def __init__(self) -> None:
        self.k = C.WinDLL("kernel32", use_last_error=True)
        self.k.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
        self.k.CreateFileW.restype = W.HANDLE
        self.k.DeviceIoControl.argtypes = [
            W.HANDLE, W.DWORD, C.c_void_p, W.DWORD, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p
        ]
        self.k.DeviceIoControl.restype = W.BOOL
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.k.CloseHandle.restype = W.BOOL

    def open(self, path: str, access: int = 0):
        handle = self.k.CreateFileW(path, access, 3, None, 3, 0, None)
        if handle == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        return handle

    def identify(self, handle) -> dict:
        query = C.create_string_buffer(12)
        out = C.create_string_buffer(4096)
        returned = W.DWORD()
        if not self.k.DeviceIoControl(handle, IOCTL_STORAGE_QUERY_PROPERTY, query, 12, out, len(out), C.byref(returned), None):
            raise C.WinError(C.get_last_error())
        return descriptor(out.raw[: returned.value])

    def request(self, handle, name: str) -> dict:
        if name not in COMMANDS:
            raise ValueError(f"Unknown command {name}")
        cdb, length = COMMANDS[name]
        if cdb[0] not in READ_OPCODES:
            raise ValueError("Refusing non-read SCSI opcode")
        sense_offset = C.sizeof(SPT)
        data_offset = (sense_offset + 32 + 7) & ~7
        packet = C.create_string_buffer(data_offset + max(length, 1))
        header = SPT.from_buffer(packet)
        header.Length = C.sizeof(SPT)
        header.CdbLength = len(cdb)
        header.SenseInfoLength = 32
        header.DataIn = 1 if length else 2
        header.DataTransferLength = length
        header.TimeOutValue = 2
        header.DataBufferOffset = data_offset if length else 0
        header.SenseInfoOffset = sense_offset
        header.Cdb[: len(cdb)] = cdb
        returned = W.DWORD()
        start = time.monotonic()
        ok = self.k.DeviceIoControl(handle, IOCTL_SCSI_PASS_THROUGH, packet, len(packet), packet, len(packet), C.byref(returned), None)
        error = 0 if ok else C.get_last_error()
        result = {
            "command": name,
            "ioctl_ok": bool(ok),
            "winerror": error,
            "elapsed_ms": round((time.monotonic() - start) * 1000),
        }
        if not ok:
            result["error"] = C.FormatError(error).strip()
            return result
        if returned.value < C.sizeof(SPT):
            result["error"] = "Truncated SCSI response header"
            return result
        count = min(length, header.DataTransferLength, max(0, returned.value - data_offset))
        data = packet.raw[data_offset : data_offset + count]
        sense_end = min(sense_offset + 32, returned.value)
        result.update(status=header.ScsiStatus, sense=sense_decode(packet.raw[sense_offset:sense_end]), transferred=count, data_hex=data.hex())
        if header.ScsiStatus == 0:
            if name == "inquiry" and len(data) >= 36:
                result["identity"] = data[8:36].decode("ascii", "replace").strip()
            elif name in ("model_id", "storage_gb") and len(data) == 4:
                result["value"] = int.from_bytes(data, "big")
            elif name == "product_id":
                result["value"] = data.rstrip(b"\0").decode("ascii", "replace")
            elif name == "capacity10" and len(data) == 8:
                last, block = struct.unpack(">II", data)
                result.update(last_lba=last, block_bytes=block)
                if last != 0xFFFFFFFF and block:
                    result["capacity_bytes"] = (last + 1) * block
            elif name == "capacity16" and len(data) >= 12:
                last, block = struct.unpack_from(">QI", data)
                result.update(last_lba=last, block_bytes=block)
                if block:
                    result["capacity_bytes"] = (last + 1) * block
            elif name == "service_devinfo" and data.startswith(b"DEVINFO"):
                result.update(parse_devinfo(data))
        return result
