"""
Upload page: drop zone + browse button + process button.
Runs PDF extraction and bill detection in a background thread.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from core.pdf_extractor import PdfExtractor
from core.bill_detector import BillDetector
from core.table_builder import TableBuilder
from patterns.pattern_manager import PatternManager

if TYPE_CHECKING:
    from ui.app_window import AppWindow

# Shared singleton services
_extractor = PdfExtractor()
_pm = PatternManager()
_detector = BillDetector(_pm)
_builder = TableBuilder()


class UploadPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, app: "AppWindow") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._processing = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Title
        ctk.CTkLabel(
            center,
            text="Upload Telecom Bill PDF",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            center,
            text="Supports PDF files up to 80 pages. Text is extracted character-by-character.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
        ).pack(pady=(0, 24))

        # Drop zone
        self._drop_frame = ctk.CTkFrame(
            center,
            width=480,
            height=180,
            border_width=2,
            border_color=("gray70", "gray40"),
            corner_radius=12,
        )
        self._drop_frame.pack(pady=(0, 20))
        self._drop_frame.pack_propagate(False)

        self._drop_icon = ctk.CTkLabel(
            self._drop_frame,
            text="📄",
            font=ctk.CTkFont(size=40),
        )
        self._drop_icon.place(relx=0.5, rely=0.3, anchor="center")

        self._drop_label = ctk.CTkLabel(
            self._drop_frame,
            text="Drag & drop a PDF here\nor click Browse",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray65"),
            justify="center",
        )
        self._drop_label.place(relx=0.5, rely=0.62, anchor="center")

        # Enable drag-and-drop via tkinter DND (Windows only, best-effort)
        try:
            self._drop_frame.drop_target_register("DND_Files")
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

        # File name display
        self._file_label = ctk.CTkLabel(
            center,
            text="No file selected",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self._file_label.pack(pady=(0, 6))

        # Page count display
        self._page_label = ctk.CTkLabel(
            center,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self._page_label.pack(pady=(0, 16))

        # Buttons
        btn_row = ctk.CTkFrame(center, fg_color="transparent")
        btn_row.pack(pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text="Browse PDF",
            width=140,
            command=self._browse,
        ).pack(side="left", padx=8)

        self._process_btn = ctk.CTkButton(
            btn_row,
            text="Process",
            width=140,
            state="disabled",
            command=self._start_processing,
        )
        self._process_btn.pack(side="left", padx=8)

        # Progress
        self._progress_bar = ctk.CTkProgressBar(center, width=480)
        self._progress_bar.set(0)
        self._progress_bar.pack(pady=(0, 8))

        self._status_label = ctk.CTkLabel(
            center,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._status_label.pack()

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a PDF file",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._load_file(path)

    def _on_drop(self, event) -> None:
        path = event.data.strip().strip("{}")
        if path.lower().endswith(".pdf"):
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        self.app.state["pdf_path"] = path
        name = Path(path).name
        self._file_label.configure(text=name)
        self._drop_label.configure(text=name)
        self._drop_frame.configure(border_color=("#2563EB", "#3B82F6"))

        # Get page count in background
        def count_pages() -> None:
            try:
                count = _extractor.page_count(path)
                self.after(0, lambda: self._page_label.configure(
                    text=f"{count} page{'s' if count != 1 else ''}"))
            except Exception:
                pass

        threading.Thread(target=count_pages, daemon=True).start()
        self._process_btn.configure(state="normal")
        self._set_status("")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _start_processing(self) -> None:
        if self._processing:
            return
        path = self.app.state.get("pdf_path")
        if not path:
            messagebox.showerror("No file", "Please select a PDF file first.")
            return

        self._processing = True
        self._process_btn.configure(state="disabled", text="Processing...")
        self._progress_bar.set(0)
        self._set_status("Reading PDF...")

        threading.Thread(target=self._process_pdf, args=(path,), daemon=True).start()

    def _process_pdf(self, path: str) -> None:
        try:
            # Collect all pages first to get total count for progress
            pages = []
            total_pages = _extractor.page_count(path)

            def page_cb(current: int, total: int) -> None:
                self.after(0, lambda: self._progress_bar.set(current / total * 0.6))
                self.after(0, lambda: self._set_status(
                    f"Extracting page {current} of {total}..."))

            for page_text in _extractor.extract_pages(path, page_callback=page_cb):
                pages.append(page_text)

            self.after(0, lambda: self._set_status("Detecting bill type..."))

            # Combine all page text for detection
            full_text = "\n".join(p.raw_text for p in pages)
            bill_type = _detector.detect(full_text)

            if bill_type is None:
                self.after(0, lambda: self._handle_unknown_bill(pages, full_text))
                return

            schema = _pm.get_schema(bill_type)
            self.after(0, lambda: self._set_status(
                f"Detected: {schema.display_name}. Building table..."))

            # Build table
            def progress_cb(rows: int) -> None:
                self.after(0, lambda: self._progress_bar.set(0.6 + rows / 1000 * 0.4))

            df = _builder.build(iter(pages), schema, progress_callback=progress_cb)

            self.app.state.update({
                "bill_type": bill_type,
                "schema": schema,
                "dataframe": df,
                "accuracy_report": None,
                "sample_rows": None,
            })

            self.after(0, self._on_success, schema.display_name, len(df))

        except Exception as exc:
            self.after(0, lambda: self._on_error(str(exc)))

    def _handle_unknown_bill(self, pages: list, full_text: str) -> None:
        self._set_status("Unknown bill type — opening Gemini portal...")
        self._processing = False
        self._process_btn.configure(state="normal", text="Process")
        self._progress_bar.set(0)

        self.app.state["_pages_cache"] = pages
        self.app.state["_full_text"] = full_text
        self.app.show_gemini_portal()

    def _on_success(self, display_name: str, row_count: int) -> None:
        self._processing = False
        self._process_btn.configure(state="normal", text="Process")
        self._progress_bar.set(1.0)
        self._set_status(
            f"Done — {display_name} | {row_count} rows extracted. "
            "Navigate to Preview to review."
        )
        self.app.show_page("preview")

    def _on_error(self, message: str) -> None:
        self._processing = False
        self._process_btn.configure(state="normal", text="Process")
        self._progress_bar.set(0)
        self._set_status(f"Error: {message}")
        messagebox.showerror("Processing Error", message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def on_show(self) -> None:
        pass
