"""
AuditSessionPage — lets the user load 1–3 bill PDFs (same carrier) and
kick off the full 8-category audit.  Each slot has its own PDF picker,
auto-detected bill type badge, and a month-label entry.
"""
from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk
import pandas as pd

if TYPE_CHECKING:
    from ui.app_window import AppWindow

MAX_SLOTS = 3

_SEVERITY_COLOR = {
    "high":   ("#dc2626", "#ef4444"),
    "medium": ("#ea580c", "#f97316"),
    "low":    ("#ca8a04", "#eab308"),
    "info":   ("#2563eb", "#60a5fa"),
}


class _BillSlot(ctk.CTkFrame):
    """One upload slot: drop / browse + month label + status badge."""

    def __init__(self, master, slot_index: int, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        self.slot_index  = slot_index
        self.pdf_path:  str | None = None
        self.bill_type: str | None = None
        self.dataframe: pd.DataFrame | None = None

        self.grid_columnconfigure(1, weight=1)

        # Slot number label
        ctk.CTkLabel(
            self, text=f"Bill {slot_index + 1}",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=52, anchor="center",
        ).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=12, sticky="ns")

        # File path display
        self._path_var = ctk.StringVar(value="No file selected")
        ctk.CTkLabel(
            self, textvariable=self._path_var,
            anchor="w", font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).grid(row=0, column=1, padx=4, pady=(12, 2), sticky="ew")

        # Month label entry
        lbl_frame = ctk.CTkFrame(self, fg_color="transparent")
        lbl_frame.grid(row=1, column=1, padx=4, pady=(0, 10), sticky="ew")
        ctk.CTkLabel(lbl_frame, text="Month label:", font=ctk.CTkFont(size=11)).pack(side="left")
        self._month_var = ctk.StringVar(value=f"Month {slot_index + 1}")
        ctk.CTkEntry(
            lbl_frame, textvariable=self._month_var,
            width=140, height=28, font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(6, 0))

        # Status badge
        self._status_lbl = ctk.CTkLabel(
            self, text="—", width=120,
            font=ctk.CTkFont(size=11),
            anchor="center",
            text_color=("gray50", "gray50"),
        )
        self._status_lbl.grid(row=0, column=2, rowspan=2, padx=8, pady=12)

        # Browse button
        ctk.CTkButton(
            self, text="Browse…", width=100, height=36,
            font=ctk.CTkFont(size=12),
            command=self._browse,
        ).grid(row=0, column=3, rowspan=2, padx=(0, 12), pady=12)

    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title=f"Select Bill {self.slot_index + 1} PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        self.pdf_path = path
        short = Path(path).name
        self._path_var.set(short if len(short) <= 40 else "…" + short[-37:])
        self._set_status("Queued", ("gray50", "gray50"))

    def set_processing(self) -> None:
        self._set_status("Processing…", ("gray50", "gray50"))

    def set_done(self, bill_type: str | None) -> None:
        self.bill_type = bill_type
        label = bill_type or "Unknown"
        color = ("#16a34a", "#22c55e") if bill_type else ("#dc2626", "#ef4444")
        self._set_status(label, color)

    def set_error(self, msg: str) -> None:
        self._set_status(f"Error: {msg[:20]}", ("#dc2626", "#ef4444"))

    def _set_status(self, text: str, color: tuple) -> None:
        self._status_lbl.configure(text=text, text_color=color)

    @property
    def month_label(self) -> str:
        return self._month_var.get().strip() or f"Month {self.slot_index + 1}"

    def clear(self) -> None:
        self.pdf_path  = None
        self.bill_type = None
        self.dataframe = None
        self._path_var.set("No file selected")
        self._month_var.set(f"Month {self.slot_index + 1}")
        self._set_status("—", ("gray50", "gray50"))


class AuditSessionPage(ctk.CTkFrame):
    """Page that manages the multi-bill audit upload session."""

    def __init__(self, master, app: "AppWindow", **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._slots: list[_BillSlot] = []
        self._worker: threading.Thread | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 4))
        ctk.CTkLabel(
            hdr, text="Telecom Bill Audit",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            hdr,
            text="Upload up to 3 months of the same carrier's bills to run a full 8-category audit.",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(self, height=1, fg_color=("gray80", "gray30")).grid(
            row=1, column=0, sticky="ew", padx=24, pady=(8, 16))

        # Slots
        slots_frame = ctk.CTkFrame(self, fg_color="transparent")
        slots_frame.grid(row=2, column=0, sticky="ew", padx=32)
        slots_frame.grid_columnconfigure(0, weight=1)

        for i in range(MAX_SLOTS):
            slot = _BillSlot(slots_frame, slot_index=i)
            slot.grid(row=i, column=0, sticky="ew", pady=6)
            self._slots.append(slot)

        # Info note for slot 1
        ctk.CTkLabel(
            slots_frame,
            text="Bill 1 is required. Bills 2 & 3 are optional but enable trend analysis.",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"),
        ).grid(row=MAX_SLOTS, column=0, sticky="w", pady=(4, 0))

        # Bottom bar
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", padx=32, pady=24)
        bar.grid_columnconfigure(0, weight=1)

        self._status_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            bar, textvariable=self._status_var,
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).grid(row=0, column=0, sticky="w")

        self._progress = ctk.CTkProgressBar(bar, width=300, height=8)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._progress.grid_remove()

        self._run_btn = ctk.CTkButton(
            bar, text="Run Audit →",
            width=160, height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_audit,
        )
        self._run_btn.grid(row=0, column=1, rowspan=2, padx=(16, 0))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        pass  # nothing to refresh on revisit

    # ------------------------------------------------------------------
    # Audit workflow
    # ------------------------------------------------------------------

    def _start_audit(self) -> None:
        filled = [s for s in self._slots if s.pdf_path]
        if not filled:
            self._set_status("Please select at least one PDF file.", error=True)
            return

        self._run_btn.configure(state="disabled")
        self._progress.set(0)
        self._progress.grid()
        self._set_status("Loading PDFs…")

        self._worker = threading.Thread(target=self._audit_worker, args=(filled,), daemon=True)
        self._worker.start()

    def _audit_worker(self, slots: list[_BillSlot]) -> None:
        from core.pdf_extractor import PdfExtractor
        from core.bill_detector import BillDetector
        from core.table_builder import TableBuilder
        from core.audit_engine import AuditEngine
        from patterns.pattern_manager import PatternManager

        try:
            pm       = PatternManager()
            pm.load()
            extractor = PdfExtractor()
            detector  = BillDetector(pm)
            builder   = TableBuilder(pm)

            dataframes:   list[pd.DataFrame] = []
            month_labels: list[str]           = []
            detected_type: str | None         = None

            total = len(slots)
            for idx, slot in enumerate(slots):
                self._ui(slot.set_processing)
                self._set_status(f"Extracting Bill {idx + 1} of {total}…")
                self._set_progress((idx * 2) / (total * 2 + 2))

                pages     = list(extractor.extract_pages(slot.pdf_path))
                full_text = "\n".join(p.raw_text for p in pages)

                bill_type = detector.detect(full_text)
                self._ui(lambda bt=bill_type: slot.set_done(bt))

                if bill_type is None:
                    self._ui(lambda: self._set_status(
                        "Unrecognised bill type on one of the PDFs. "
                        "Process each bill individually first to set up patterns.",
                        error=True,
                    ))
                    self._ui(lambda: self._run_btn.configure(state="normal"))
                    self._ui(lambda: self._progress.grid_remove())
                    return

                if detected_type is None:
                    detected_type = bill_type
                elif bill_type != detected_type:
                    self._ui(lambda: self._set_status(
                        "All bills must be from the same carrier / bill type.", error=True))
                    self._ui(lambda: self._run_btn.configure(state="normal"))
                    self._ui(lambda: self._progress.grid_remove())
                    return

                schema = pm.get_schema(bill_type)
                self._set_status(f"Building table for Bill {idx + 1}…")
                self._set_progress((idx * 2 + 1) / (total * 2 + 2))

                df = builder.build(iter(pages), schema)
                slot.dataframe = df
                dataframes.append(df)
                month_labels.append(slot.month_label)

            self._set_status("Running audit analysis…")
            self._set_progress((total * 2) / (total * 2 + 2))

            engine = AuditEngine(dataframes, month_labels, bill_type=detected_type)
            report = engine.run()

            self._set_progress(1.0)
            self._ui(lambda: self._on_audit_done(report, detected_type, dataframes, month_labels))

        except Exception as exc:  # noqa: BLE001
            self._ui(lambda e=exc: self._set_status(f"Error: {e}", error=True))
            self._ui(lambda: self._run_btn.configure(state="normal"))
            self._ui(lambda: self._progress.grid_remove())

    def _on_audit_done(
        self,
        report,
        bill_type: str,
        dataframes: list[pd.DataFrame],
        month_labels: list[str],
    ) -> None:
        self.app.state["audit_report"]   = report
        self.app.state["audit_dfs"]      = dataframes
        self.app.state["audit_labels"]   = month_labels
        self.app.state["bill_type"]      = bill_type
        self._run_btn.configure(state="normal")
        self._progress.grid_remove()
        self._set_status("")
        self.app.show_audit_results()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        def _do():
            self._status_var.set(msg)
        self.after(0, _do)

    def _set_progress(self, value: float) -> None:
        self.after(0, lambda: self._progress.set(value))

    def _ui(self, fn) -> None:
        self.after(0, fn)
