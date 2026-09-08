"""Simple Thai-first recovery window. One action at a time."""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from walkman_recovery import __version__
from walkman_recovery.detect import Snapshot, snapshot
from walkman_recovery.elevate import is_admin, relaunch
from walkman_recovery.msc import clean_walkman_one
from walkman_recovery.paths import mtk_dir
from walkman_recovery.recovery import RecoveryError, reboot_device, repair_contents, restore_boot
from walkman_recovery.updater import find_stock_packages, launch

BG = "#101214"
CARD = "#1b1f24"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
ACCENT = "#f97316"
OK = "#34d399"
WARN = "#fbbf24"
BAD = "#fb7185"
BTN = "#292f36"


def _size(n: int | None) -> str:
    if not n:
        return "-"
    gb = n / (1000 ** 3)
    return f"{gb:.1f} GB"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WM1 Recovery")
        self.root.geometry("920x680")
        self.root.minsize(820, 600)
        self.root.configure(bg=BG)
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
        self.state: Snapshot | None = None
        self.original_boot: Path | None = None
        self._build()
        self.root.after(200, self.refresh)
        self.root.after(120, self._poll)

    def _build(self) -> None:
        pad = {"padx": 20, "pady": 8}
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", **pad)
        tk.Label(header, text="WM1 Recovery", fg=TEXT, bg=BG, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="กู้ Sony Walkman NW-WM1A / WM1Z บน Windows  ·  ไม่แตะดิสก์เครื่องคอมพิวเตอร์",
            fg=MUTED, bg=BG, font=("Segoe UI", 11),
        ).pack(anchor="w")

        self.card = tk.Frame(self.root, bg=CARD)
        self.card.pack(fill="x", padx=20, pady=4)
        inner = tk.Frame(self.card, bg=CARD)
        inner.pack(fill="x", padx=18, pady=16)
        self.status = tk.StringVar(value="กำลังตรวจเครื่อง...")
        self.detail = tk.StringVar(value="")
        tk.Label(inner, textvariable=self.status, fg=TEXT, bg=CARD, font=("Segoe UI", 18, "bold"), wraplength=840, justify="left").pack(anchor="w")
        tk.Label(inner, textvariable=self.detail, fg=MUTED, bg=CARD, font=("Segoe UI", 11), wraplength=840, justify="left").pack(anchor="w", pady=(6, 0))

        self.hint = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.hint, fg=WARN, bg=BG, font=("Segoe UI", 11), wraplength=860, justify="left").pack(fill="x", padx=22, pady=(4, 8))

        grid = tk.Frame(self.root, bg=BG)
        grid.pack(fill="x", padx=20)
        self.buttons = {}
        specs = [
            ("detect", "ตรวจเครื่อง", self.refresh),
            ("clean", "ลบไฟล์ Walkman One", self.clean),
            ("repair", "กู้พาร์ติชันเพลง", self.repair),
            ("stock", "กลับเฟิร์มสต็อก", self.stock),
            ("restore", "คืน boot เดิม", self.restore),
        ]
        for i, (key, label, cmd) in enumerate(specs):
            btn = tk.Button(
                grid, text=label, command=cmd, bg=BTN, fg=TEXT, activebackground=ACCENT,
                activeforeground=TEXT, relief="flat", font=("Segoe UI", 12, "bold"),
                padx=12, pady=12, cursor="hand2",
            )
            btn.grid(row=0, column=i, sticky="ew", padx=4, pady=4)
            grid.columnconfigure(i, weight=1)
            self.buttons[key] = btn

        tk.Label(self.root, text="บันทึกการทำงาน", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(12, 0))
        self.log = ScrolledText(self.root, height=14, bg="#0b0d10", fg="#d1d5db", insertbackground=TEXT, font=("Consolas", 10), relief="flat")
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 16))

    def write(self, line: str) -> None:
        self.messages.put(("log", line))

    def _poll(self) -> None:
        while not self.messages.empty():
            kind, payload = self.messages.get_nowait()
            if kind == "log":
                self.log.insert("end", payload + "\n")
                self.log.see("end")
            elif kind == "state":
                self._apply(payload)
            elif kind == "busy":
                self.busy = payload
                self._enable()
            elif kind == "boot":
                self.original_boot = payload
        self.root.after(120, self._poll)

    def _apply(self, state: Snapshot) -> None:
        self.state = state
        self.status.set(state.summary)
        bits = []
        if not state.admin:
            bits.append("ยังไม่ใช่ Administrator")
        if state.luns:
            lun = state.luns[0]
            bits.append(f"serial {lun.serial}")
            if lun.reported_model:
                bits.append(lun.reported_model)
            if lun.firmware:
                bits.append(lun.firmware)
            if lun.capacity_bytes:
                bits.append(_size(lun.capacity_bytes))
            elif lun.sense:
                bits.append(lun.sense)
        if state.volumes:
            vol = state.walkman_volume
            bits.append(f"ไดรฟ์ {vol.letter}: {vol.label or vol.filesystem}")
            if vol.has_cfw:
                bits.append("พบโฟลเดอร์ CFW")
        if state.usb and not bits:
            bits.append(state.usb[0].split("|")[-1])
        if not state.mtk_ready:
            bits.append("ยังไม่มี flash_tool.exe / DA.bin")
        self.detail.set("  ·  ".join(bits) if bits else "เสียบ Walkman แล้วกดตรวจเครื่อง")
        self.hint.set(state.instruction)
        self._enable()

    def _enable(self) -> None:
        state = self.state
        can = not self.busy
        self.buttons["detect"].configure(state="normal" if can else "disabled")
        clean = can and state and state.walkman_volume and state.walkman_volume.has_cfw
        self.buttons["clean"].configure(state="normal" if clean else "disabled")
        repair = can and state and state.mode in {"preloader", "no_media", "missing", "usb"}
        self.buttons["repair"].configure(state="normal" if repair else "disabled")
        stock = can and state and state.mode == "cfw" and state.walkman_volume
        self.buttons["stock"].configure(state="normal" if stock else "disabled")
        restore = can and self.original_boot is not None
        self.buttons["restore"].configure(state="normal" if restore else "disabled")

    def _work(self, fn) -> None:
        if self.busy:
            return
        self.busy = True
        self._enable()

        def runner():
            try:
                fn()
            except Exception as exc:
                self.write(f"ผิดพลาด: {exc}")
            finally:
                try:
                    self.messages.put(("state", snapshot()))
                except Exception as exc:
                    self.write(f"ตรวจเครื่องไม่สำเร็จ: {exc}")
                self.messages.put(("busy", False))

        threading.Thread(target=runner, daemon=True).start()

    def refresh(self) -> None:
        def work():
            self.write("ตรวจ USB / SCSI / ไดรฟ์เพลง...")
            state = snapshot()
            self.messages.put(("state", state))
            self.write(f"สถานะ: {state.mode} — {state.summary}")

        self._work(work)

    def clean(self) -> None:
        state = self.state
        if not state or not state.walkman_volume:
            return
        vol = state.walkman_volume
        if not messagebox.askyesno("ลบไฟล์ Walkman One", f"จะลบโฟลเดอร์ CFW และ wm1a-repair.log บนไดรฟ์ {vol.letter}: เท่านั้น\nไม่ลบเพลงใน MUSIC และไม่ฟอร์แมต"):
            return

        def work():
            removed = clean_walkman_one(vol)
            if removed:
                for path in removed:
                    self.write(f"ลบ {path}")
            else:
                self.write("ไม่พบไฟล์ Walkman One ค้างอยู่")

        self._work(work)

    def repair(self) -> None:
        if mtk_dir() is None:
            messagebox.showerror("ยังไม่มีเครื่องมือแฟลช", "วาง flash_tool.exe และ DA.bin ในโฟลเดอร์ vendor\\mtk ตาม README")
            return
        if not messagebox.askyesno(
            "กู้พาร์ติชันเพลง",
            "ขั้นตอนนี้จะสำรอง boot ของเครื่องนี้ แล้วเขียน boot ซ่อมชั่วคราวเพื่อให้ Sony format_contents ล้างพาร์ติชันเพลง\n"
            "เพลงในเครื่องจะถูกลบ\n\nต้องเข้าโหมด Preloader ก่อน: กดค้าง Volume Down + Play แล้วกด Power 8–10 วินาที",
        ):
            return

        def work():
            self.write("รอ Preloader แล้วสำรอง/เขียน boot ซ่อม...")
            original = repair_contents(self.write, stage2=False)
            self.messages.put(("boot", original))
            self.write("อ่านกลับตรงแล้ว จะรีบูตให้เครื่องฟอร์แมตพาร์ติชันเพลง")
            reboot_device(self.write)
            self.write("รีบูตแล้ว ดูหน้าจอเครื่อง อย่าถอดสาย จนกว่าไดรฟ์ WALKMAN จะโผล่")

        self._work(work)

    def restore(self) -> None:
        if self.original_boot is None:
            return
        if not messagebox.askyesno("คืน boot เดิม", "ต้องอยู่ใน Preloader / DA stage 2 เพื่อเขียน boot เดิมกลับ และอ่านกลับเทียบก่อนรีบูต"):
            return

        def work():
            restore_boot(self.original_boot, self.write, stage2=True)
            reboot_device(self.write)
            self.write("คืน boot เดิมแล้ว")

        self._work(work)

    def stock(self) -> None:
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์ที่มี StockRevert และไฟล์ Sony 3.02")
        if not folder:
            return
        revert, official = find_stock_packages(Path(folder))
        if revert is None:
            messagebox.showerror("ไม่พบ StockRevert", "ต้องมีไฟล์ชื่อประมาณ 1_StockRevert_Walkman_One_WM1.exe")
            return
        if not messagebox.askyesno("กลับเฟิร์มสต็อก", f"จะเปิดตัวติดตั้ง:\n{revert.name}\nจากนั้นเปิด {official.name if official else 'Sony 3.02 (ถ้ามี)'}\nอย่าถอดสายระหว่างแถบอัปเดต"):
            return

        def work():
            self.write(f"เปิด {revert}")
            proc = launch(revert)
            proc.wait()
            self.write("StockRevert ปิดแล้ว")
            if official:
                self.write("รอให้ไดรฟ์ Walkman กลับมา แล้วเปิด Sony 3.02...")
                import time
                for _ in range(60):
                    state = snapshot()
                    if state.walkman_volume:
                        break
                    time.sleep(2)
                self.write(f"เปิด {official}")
                launch(official).wait()
                self.write("ตัวติดตั้ง Sony ปิดแล้ว")

        self._work(work)


def main() -> None:
    if relaunch():
        return
    root = tk.Tk()
    App(root)
    if not is_admin():
        messagebox.showwarning("สิทธิ์ Administrator", "เปิดด้วยสิทธิ์แอดมินจะคุยกับ Walkman ได้ครบกว่า")
    root.mainloop()
