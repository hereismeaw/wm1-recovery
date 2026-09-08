"""Classify the currently attached Walkman or Preloader. Read-only."""
from __future__ import annotations

from dataclasses import dataclass, field
import subprocess

from walkman_recovery.msc import Volume
from walkman_recovery.scsi import MODEL_IDS, WindowsSCSI, is_walkman


@dataclass
class Lun:
    path: str
    serial: str
    inquiry: str = ""
    ready: bool = False
    capacity_bytes: int | None = None
    model_id: int | None = None
    model_name: str = ""
    storage_gb: int | None = None
    product_id: str = ""
    firmware: str = ""
    reported_model: str = ""
    sense: str = ""


@dataclass
class Snapshot:
    admin: bool
    mode: str
    summary: str
    instruction: str
    usb: list[str] = field(default_factory=list)
    luns: list[Lun] = field(default_factory=list)
    volumes: list[Volume] = field(default_factory=list)
    mtk_ready: bool = False

    @property
    def walkman_volume(self) -> Volume | None:
        labeled = [v for v in self.volumes if v.label.upper() == "WALKMAN"]
        return labeled[0] if labeled else (self.volumes[0] if self.volumes else None)


def _pnp_ids() -> list[str]:
    command = (
        "Get-PnpDevice -PresentOnly | Where-Object { "
        "$_.InstanceId -match 'VID_0E8D|VID_054C' -or $_.FriendlyName -match 'WALKMAN|Preloader|MT65' "
        "} | ForEach-Object { $_.Status + '|' + $_.FriendlyName + '|' + $_.InstanceId }"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _probe_luns() -> list[Lun]:
    api = WindowsSCSI()
    found: list[Lun] = []
    for index in range(32):
        path = rf"\\.\PhysicalDrive{index}"
        try:
            handle = api.open(path)
        except OSError:
            continue
        try:
            info = api.identify(handle)
        except (OSError, ValueError):
            continue
        finally:
            api.k.CloseHandle(handle)
        if not is_walkman(info):
            continue
        lun = Lun(path=path, serial=info["serial"])
        try:
            handle = api.open(path, 0xC0000000)
        except OSError:
            found.append(lun)
            continue
        try:
            if not is_walkman(api.identify(handle)):
                continue
            inquiry = api.request(handle, "inquiry")
            lun.inquiry = inquiry.get("identity") or ""
            ready = api.request(handle, "ready")
            lun.ready = ready.get("status") == 0
            if not lun.ready and ready.get("sense"):
                lun.sense = ready["sense"].get("meaning", "")
            cap = api.request(handle, "capacity10")
            lun.capacity_bytes = cap.get("capacity_bytes")
            model = api.request(handle, "model_id")
            if model.get("status") == 0:
                lun.model_id = model.get("value")
                lun.model_name = MODEL_IDS.get(lun.model_id, f"unknown:{lun.model_id:#x}")
            storage = api.request(handle, "storage_gb")
            if storage.get("status") == 0:
                lun.storage_gb = storage.get("value")
            product = api.request(handle, "product_id")
            lun.product_id = product.get("value") or ""
            devinfo = api.request(handle, "service_devinfo")
            if devinfo.get("status") == 0:
                lun.reported_model = devinfo.get("model") or ""
                lun.firmware = devinfo.get("firmware") or ""
        except (OSError, ValueError):
            pass
        finally:
            api.k.CloseHandle(handle)
        found.append(lun)
    return found


def snapshot() -> Snapshot:
    from walkman_recovery.msc import list_walkman_volumes
    from walkman_recovery.paths import mtk_dir

    admin = _is_admin()
    usb = _pnp_ids()
    preloader = any("VID_0E8D&PID_2000" in row or "Preloader" in row for row in usb)
    walkman_usb = any("VID_054C" in row for row in usb)
    luns = _probe_luns() if walkman_usb else []
    volumes = list_walkman_volumes() if walkman_usb else []
    mtk_ready = mtk_dir() is not None

    if preloader and not walkman_usb:
        mode = "preloader"
        summary = "พบโหมด Preloader (MediaTek)"
        instruction = (
            "เครื่องอยู่ในโหมดดาวน์โหลดแล้ว กด «กู้พาร์ติชันเพลง» เพื่อสำรอง boot แล้วฟอร์แมตไดรฟ์เพลงผ่านสคริปต์ของ Sony"
        )
    elif not walkman_usb:
        mode = "missing"
        summary = "ยังไม่พบ Walkman"
        instruction = (
            "เสียบ USB แล้วเปิดเครื่อง หากวนโลโก้ ให้เข้า Preloader: "
            "กดค้าง Volume Down + Play แล้วกด Power 8–10 วินาที โดยยังไม่ปล่อยปุ่มแรก"
        )
    else:
        primary = next((lun for lun in luns if lun.ready), luns[0] if luns else None)
        cfw = any(v.has_cfw for v in volumes)
        pid_cfw = any("PID_0BC1" in row for row in usb)
        model = (primary.reported_model if primary else "") or (primary.model_name if primary else "")
        fw = primary.firmware if primary else ""
        if primary and primary.ready and not pid_cfw and not cfw:
            mode = "stock"
            summary = f"สต็อก {model or 'WALKMAN'}  {fw}".strip()
            instruction = "เครื่องพร้อมใช้งาน สามารถลบไฟล์ค้างของ Walkman One ได้ถ้ายังเหลือ"
        elif primary and primary.ready and (pid_cfw or cfw):
            mode = "cfw"
            summary = f"Walkman One / CFW  {model}  {fw}".strip()
            instruction = "กด «กลับเฟิร์มสต็อก» เพื่อรัน StockRevert แล้วตามด้วย Sony 3.02 หรือลบโฟลเดอร์ CFW อย่างเดียว"
        elif primary and not primary.ready:
            mode = "no_media"
            summary = "เชื่อม USB ได้ แต่ยังไม่มีสื่อเพลง"
            instruction = (
                "มักเกิดตอนวนโลโก้เพราะพาร์ติชันเพลงเสีย กด «กู้พาร์ติชันเพลง» แล้วเข้า Preloader ตามคำแนะนำ"
            )
        else:
            mode = "usb"
            summary = "พบ USB Walkman"
            instruction = "กด «ตรวจเครื่อง» อีกครั้ง หรือเข้า Preloader ถ้าเครื่องยังวนโลโก้"
    return Snapshot(
        admin=admin, mode=mode, summary=summary, instruction=instruction,
        usb=usb, luns=luns, volumes=volumes, mtk_ready=mtk_ready,
    )
