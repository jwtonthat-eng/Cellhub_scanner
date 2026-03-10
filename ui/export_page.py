"""
Export page: CSV/Excel format selection, file path picker, export button,
and post-export Google Drive upload prompt.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.exporter import Exporter

if TYPE_CHECKING:
    from ui.app_window import AppWindow


class ExportPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, app: "AppWindow") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(
            center,
            text="Export Extracted Data",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            center,
            text="Choose a format and destination for the extracted table.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        ).pack(pady=(0, 24))

        # Format selection
        format_frame = ctk.CTkFrame(center)
        format_frame.pack(fill="x", pady=(0, 20), padx=4)

        ctk.CTkLabel(
            format_frame,
            text="Export format",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        self._format_var = ctk.StringVar(value="excel")

        rb_row = ctk.CTkFrame(format_frame, fg_color="transparent")
        rb_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkRadioButton(
            rb_row,
            text="Excel (.xlsx)  — includes metadata sheet",
            variable=self._format_var,
            value="excel",
            command=self._update_path_extension,
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            rb_row,
            text="CSV (.csv)",
            variable=self._format_var,
            value="csv",
            command=self._update_path_extension,
        ).pack(side="left")

        # File path
        path_frame = ctk.CTkFrame(center)
        path_frame.pack(fill="x", pady=(0, 20), padx=4)

        ctk.CTkLabel(
            path_frame,
            text="Save to",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 6))

        path_row = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=16, pady=(0, 12))
        path_row.grid_columnconfigure(0, weight=1)

        self._path_entry = ctk.CTkEntry(
            path_row,
            placeholder_text="Choose export location...",
            height=36,
        )
        self._path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            path_row,
            text="Browse",
            width=90,
            command=self._browse_path,
        ).grid(row=0, column=1)

        # Export button
        self._export_btn = ctk.CTkButton(
            center,
            text="Export",
            width=200,
            height=44,
            font=ctk.CTkFont(size=14),
            command=self._do_export,
        )
        self._export_btn.pack(pady=(0, 12))

        self._status_label = ctk.CTkLabel(
            center,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._status_label.pack(pady=(0, 20))

        # Drive upload card (hidden until export completes, shown for ALL bill types)
        self._drive_banner = ctk.CTkFrame(
            center,
            fg_color=("#e8f0fe", "#1c2e4a"),
            corner_radius=12,
            border_width=1,
            border_color=("#1a73e8", "#1558b0"),
        )

        drive_inner = ctk.CTkFrame(self._drive_banner, fg_color="transparent")
        drive_inner.pack(fill="x", padx=16, pady=14)
        drive_inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            drive_inner,
            text="File saved!",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#1a73e8", "#5b9cf6"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            drive_inner,
            text="Would you like to upload this file to Google Drive?",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray75"),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        ctk.CTkButton(
            drive_inner,
            text="☁  Upload to Google Drive",
            width=230,
            height=46,
            font=ctk.CTkFont(size=13),
            fg_color=("#1a73e8", "#1558b0"),
            hover_color=("#1557c0", "#0f3f7a"),
            command=self._open_drive_dialog,
        ).grid(row=0, column=1, rowspan=2, padx=(16, 0), sticky="e")

    # ------------------------------------------------------------------
    # Path handling
    # ------------------------------------------------------------------

    def _browse_path(self) -> None:
        fmt = self._format_var.get()
        bill_type = self.app.state.get("bill_type", "output")
        default_name = f"{bill_type}_extracted"

        if fmt == "excel":
            path = filedialog.asksaveasfilename(
                title="Save Excel file",
                defaultextension=".xlsx",
                initialfile=default_name,
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            )
        else:
            path = filedialog.asksaveasfilename(
                title="Save CSV file",
                defaultextension=".csv",
                initialfile=default_name,
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )

        if path:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, path)

    def _update_path_extension(self) -> None:
        current = self._path_entry.get()
        if not current:
            return
        p = Path(current)
        fmt = self._format_var.get()
        new_suffix = ".xlsx" if fmt == "excel" else ".csv"
        if p.suffix.lower() in (".xlsx", ".csv"):
            new_path = str(p.with_suffix(new_suffix))
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, new_path)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _do_export(self) -> None:
        df = self.app.state.get("dataframe")
        if df is None or df.empty:
            messagebox.showwarning("No data", "No extracted data to export. Process a PDF first.")
            return

        path = self._path_entry.get().strip()
        if not path:
            messagebox.showwarning("No path", "Please choose a save location.")
            return

        self._export_btn.configure(state="disabled", text="Exporting...")
        self._drive_banner.pack_forget()
        self._status_label.configure(text="")

        threading.Thread(target=self._run_export, args=(df, path), daemon=True).start()

    def _run_export(self, df, path: str) -> None:
        try:
            fmt = self._format_var.get()
            bill_type = self.app.state.get("bill_type", "")
            report = self.app.state.get("accuracy_report")
            accuracy = report.overall if report else None

            if fmt == "excel":
                Exporter.to_excel(df, path, bill_type=bill_type, accuracy_score=accuracy)
            else:
                Exporter.to_csv(df, path)

            self.app.state["export_path"] = path
            self.after(0, self._on_export_success, path)
        except Exception as exc:
            self.after(0, self._on_export_error, str(exc))

    def _on_export_success(self, path: str) -> None:
        self._export_btn.configure(state="normal", text="Export")
        name = Path(path).name
        self._status_label.configure(
            text=f"Saved: {name}",
            text_color=("#16a34a", "#22c55e"),
        )
        self._drive_banner.pack(fill="x", pady=(0, 4))

    def _on_export_error(self, msg: str) -> None:
        self._export_btn.configure(state="normal", text="Export")
        self._status_label.configure(
            text=f"Export failed: {msg}",
            text_color=("#dc2626", "#ef4444"),
        )
        messagebox.showerror("Export Error", msg)

    # ------------------------------------------------------------------
    # Drive upload
    # ------------------------------------------------------------------

    def _open_drive_dialog(self) -> None:
        from ui.drive_upload_dialog import DriveUploadDialog
        path = self.app.state.get("export_path")
        if not path:
            return
        dialog = DriveUploadDialog(self, file_path=path)
        dialog.grab_set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        self._drive_banner.pack_forget()
        self._status_label.configure(text="", text_color=("gray40", "gray65"))
        self._export_btn.configure(state="normal", text="Export")
