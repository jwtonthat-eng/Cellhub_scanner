"""
Pattern Editor page: review and edit Gemini-returned column patterns before saving.
Allows testing each regex against the first page of the PDF.
"""
from __future__ import annotations

import re
import threading
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from core.accuracy_scorer import AccuracyScorer
from core.table_builder import TableBuilder
from patterns.pattern_manager import PatternManager

if TYPE_CHECKING:
    from ui.app_window import AppWindow


class PatternEditorPage(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        app: "AppWindow",
        raw_dict: dict[str, Any],
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._raw_dict = raw_dict
        self._pm = PatternManager()
        self._builder = TableBuilder()
        self._column_widgets: list[dict[str, ctk.CTkEntry | ctk.CTkLabel]] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Review & Edit Regex Patterns",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header,
            text="← Back to Gemini Portal",
            width=180,
            fg_color="transparent",
            border_width=1,
            command=lambda: self.app.show_gemini_portal(),
        ).grid(row=0, column=2, sticky="e")

        # Scrollable content
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        self._scroll.grid_columnconfigure(0, weight=1)

        row = self._build_meta_section(0)
        row = self._build_row_split_section(row)
        row = self._build_columns_section(row)
        self._build_action_bar(row)

        # Footer buttons
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))

        ctk.CTkButton(
            footer,
            text="← Back",
            width=120,
            fg_color="transparent",
            border_width=1,
            command=lambda: self.app.show_gemini_portal(),
        ).pack(side="left")

        self._save_btn = ctk.CTkButton(
            footer,
            text="Save Patterns & Process PDF →",
            width=240,
            command=self._save_and_process,
        )
        self._save_btn.pack(side="right")

        self._footer_status = ctk.CTkLabel(
            footer,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._footer_status.pack(side="right", padx=12)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_meta_section(self, start_row: int) -> int:
        card = ctk.CTkFrame(self._scroll)
        card.grid(row=start_row, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Bill Type Information",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))

        fields = [
            ("Bill Type ID", "bill_type", "e.g. vodacom_monthly"),
            ("Display Name", "display_name", "e.g. Vodacom Monthly Bill"),
        ]
        self._meta_entries: dict[str, ctk.CTkEntry] = {}
        for i, (label, key, placeholder) in enumerate(fields, start=1):
            ctk.CTkLabel(card, text=label, anchor="w").grid(
                row=i, column=0, padx=(14, 8), pady=4, sticky="w")
            entry = ctk.CTkEntry(card, placeholder_text=placeholder, height=32)
            entry.grid(row=i, column=1, padx=(0, 14), pady=4, sticky="ew")
            entry.insert(0, self._raw_dict.get(key, ""))
            self._meta_entries[key] = entry

        ctk.CTkFrame(card, height=12, fg_color="transparent").grid(
            row=len(fields) + 1, column=0)
        return start_row + 1

    def _build_row_split_section(self, start_row: int) -> int:
        card = ctk.CTkFrame(self._scroll)
        card.grid(row=start_row, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Row Split Pattern",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            card,
            text=(
                "A regex that marks the START of each table row in the PDF text. "
                "Each match begins a new row."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            wraplength=600,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 8))

        self._row_split_entry = ctk.CTkEntry(
            card,
            placeholder_text="e.g. (?m)^\\s*(\\d{2}/\\d{2}/\\d{4})",
            height=32,
        )
        self._row_split_entry.grid(row=2, column=0, columnspan=2, sticky="ew",
                                   padx=(14, 8), pady=(0, 12))
        self._row_split_entry.insert(0, self._raw_dict.get("row_split_pattern", ""))

        self._row_split_test_btn = ctk.CTkButton(
            card, text="Test", width=70,
            command=self._test_row_split,
        )
        self._row_split_test_btn.grid(row=2, column=2, padx=(0, 14), pady=(0, 12))

        self._row_split_result = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray65"),
        )
        self._row_split_result.grid(row=3, column=0, columnspan=3, sticky="w",
                                    padx=14, pady=(0, 12))
        return start_row + 1

    def _build_columns_section(self, start_row: int) -> int:
        ctk.CTkLabel(
            self._scroll,
            text="Column Patterns",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=start_row, column=0, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            self._scroll,
            text=(
                "Each column pattern is applied to the text block between two row-split matches. "
                "Edit the regex and example_match fields. Click 'Test' to validate."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            wraplength=700,
            justify="left",
        ).grid(row=start_row + 1, column=0, sticky="w", pady=(0, 12))

        self._cols_container = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._cols_container.grid(row=start_row + 2, column=0, sticky="ew")
        self._cols_container.grid_columnconfigure(0, weight=1)

        self._column_widgets = []
        for i, col in enumerate(self._raw_dict.get("columns", [])):
            self._add_column_card(i, col)

        return start_row + 3

    def _add_column_card(self, idx: int, col: dict) -> None:
        card = ctk.CTkFrame(self._cols_container)
        card.grid(row=idx, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(3, weight=1)

        # Column header
        ctk.CTkLabel(
            card,
            text=f"Column {idx + 1}: {col.get('display_name', col.get('name', ''))}",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12, 6))

        # Name
        ctk.CTkLabel(card, text="Name (id)", anchor="w", width=90).grid(
            row=1, column=0, padx=(14, 6), pady=3, sticky="w")
        name_entry = ctk.CTkEntry(card, height=30)
        name_entry.insert(0, col.get("name", ""))
        name_entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=3)

        # Display name
        ctk.CTkLabel(card, text="Label", anchor="w", width=90).grid(
            row=1, column=2, padx=(0, 6), pady=3, sticky="w")
        display_entry = ctk.CTkEntry(card, height=30)
        display_entry.insert(0, col.get("display_name", ""))
        display_entry.grid(row=1, column=3, sticky="ew", padx=(0, 14), pady=3)

        # Regex
        ctk.CTkLabel(card, text="Regex", anchor="w", width=90).grid(
            row=2, column=0, padx=(14, 6), pady=3, sticky="w")
        regex_entry = ctk.CTkEntry(card, height=30)
        regex_entry.insert(0, col.get("regex", ""))
        regex_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=3)

        test_btn = ctk.CTkButton(
            card, text="Test", width=70,
            command=lambda e=regex_entry, r=idx: self._test_column_regex(e, r),
        )
        test_btn.grid(row=2, column=3, padx=(0, 14), pady=3, sticky="e")

        # Dtype + transform row
        ctk.CTkLabel(card, text="Type", anchor="w", width=90).grid(
            row=3, column=0, padx=(14, 6), pady=3, sticky="w")
        dtype_menu = ctk.CTkOptionMenu(
            card,
            values=["str", "float", "int", "date"],
            width=100,
        )
        dtype_menu.set(col.get("dtype", "str"))
        dtype_menu.grid(row=3, column=1, sticky="w", padx=(0, 12), pady=3)

        ctk.CTkLabel(card, text="Transform", anchor="w", width=90).grid(
            row=3, column=2, padx=(0, 6), pady=3, sticky="w")
        transform_menu = ctk.CTkOptionMenu(
            card,
            values=["null", "strip", "upper", "lower", "remove_commas", "remove_spaces"],
            width=140,
        )
        transform_menu.set(col.get("transform") or "null")
        transform_menu.grid(row=3, column=3, sticky="w", padx=(0, 14), pady=3)

        # Test result / status
        test_result = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray65"),
        )
        test_result.grid(row=4, column=0, columnspan=4, sticky="w",
                         padx=14, pady=(0, 12))

        self._column_widgets.append({
            "name": name_entry,
            "display_name": display_entry,
            "regex": regex_entry,
            "dtype": dtype_menu,
            "transform": transform_menu,
            "test_result": test_result,
        })

    def _build_action_bar(self, start_row: int) -> None:
        # Accuracy info placeholder
        self._accuracy_label = ctk.CTkLabel(
            self._scroll,
            text="",
            font=ctk.CTkFont(size=12),
        )
        self._accuracy_label.grid(row=start_row, column=0, sticky="w", pady=(0, 8))

    # ------------------------------------------------------------------
    # Testing
    # ------------------------------------------------------------------

    def _test_row_split(self) -> None:
        pattern = self._row_split_entry.get().strip()
        page_text = self._get_first_page_text()
        if not page_text:
            self._row_split_result.configure(
                text="No PDF loaded. Upload a PDF first.")
            return
        try:
            compiled = re.compile(pattern, re.MULTILINE)
            matches = list(compiled.finditer(page_text))
            self._row_split_result.configure(
                text=f"Found {len(matches)} row starts on first page.",
                text_color=("#16a34a" if matches else "#ea580c", "#22c55e" if matches else "#f97316"),
            )
        except re.error as exc:
            self._row_split_result.configure(
                text=f"Invalid regex: {exc}",
                text_color=("#dc2626", "#ef4444"),
            )

    def _test_column_regex(self, entry: ctk.CTkEntry, col_idx: int) -> None:
        pattern = entry.get().strip()
        page_text = self._get_first_page_text()
        result_label: ctk.CTkLabel = self._column_widgets[col_idx]["test_result"]

        if not page_text:
            result_label.configure(text="No PDF loaded.")
            return
        try:
            compiled = re.compile(pattern, re.MULTILINE)
            matches = list(compiled.finditer(page_text))
            if matches:
                examples = [m.group(1) if m.lastindex else m.group(0)
                            for m in matches[:3]]
                result_label.configure(
                    text=f"{len(matches)} matches — e.g.: " + " | ".join(examples),
                    text_color=("#16a34a", "#22c55e"),
                )
            else:
                result_label.configure(
                    text="No matches on first page.",
                    text_color=("#ea580c", "#f97316"),
                )
        except re.error as exc:
            result_label.configure(
                text=f"Invalid regex: {exc}",
                text_color=("#dc2626", "#ef4444"),
            )

    def _get_first_page_text(self) -> str:
        pages = self.app.state.get("_pages_cache")
        if pages:
            return pages[0].raw_text if pages else ""
        return ""

    # ------------------------------------------------------------------
    # Save and process
    # ------------------------------------------------------------------

    def _save_and_process(self) -> None:
        # Collect current field values
        raw = dict(self._raw_dict)
        raw["bill_type"] = self._meta_entries["bill_type"].get().strip()
        raw["display_name"] = self._meta_entries["display_name"].get().strip()
        raw["row_split_pattern"] = self._row_split_entry.get().strip()

        updated_columns = []
        for i, w in enumerate(self._column_widgets):
            transform_val = w["transform"].get()
            updated_columns.append({
                **self._raw_dict["columns"][i],
                "name": w["name"].get().strip(),
                "display_name": w["display_name"].get().strip(),
                "regex": w["regex"].get().strip(),
                "dtype": w["dtype"].get(),
                "transform": None if transform_val == "null" else transform_val,
            })
        raw["columns"] = updated_columns

        if not raw["bill_type"]:
            messagebox.showwarning("Missing field", "Bill Type ID cannot be empty.")
            return

        self._save_btn.configure(state="disabled", text="Processing...")
        self._footer_status.configure(text="Saving patterns...")

        threading.Thread(target=self._run_save_and_process, args=(raw,), daemon=True).start()

    def _run_save_and_process(self, raw: dict) -> None:
        try:
            schema, warnings = self._pm.add_bill_type(raw)
            self.after(0, lambda: self._footer_status.configure(
                text="Patterns saved. Building table..."))

            pages = self.app.state.get("_pages_cache", [])
            df = self._builder.build(iter(pages), schema)

            # Score accuracy
            sample_rows = self.app.state.get("sample_rows", [])
            report = None
            if sample_rows and not df.empty:
                scorer = AccuracyScorer()
                dtypes = {col.name: col.dtype for col in schema.columns}
                report = scorer.score(sample_rows, df, column_dtypes=dtypes)
                raw["_accuracy_score"] = report.overall
                # Update schema metadata with accuracy
                self._pm.update_bill_type(schema.bill_type, {"columns": raw["columns"]})

            self.app.state.update({
                "bill_type": schema.bill_type,
                "schema": schema,
                "dataframe": df,
                "accuracy_report": report,
            })

            self.after(0, self._on_done, len(df), report)

        except ValueError as exc:
            self.after(0, self._on_error, str(exc))
        except Exception as exc:
            self.after(0, self._on_error, f"Unexpected error: {exc}")

    def _on_done(self, row_count: int, report) -> None:
        self._save_btn.configure(state="normal", text="Save Patterns & Process PDF →")
        msg = f"Done — {row_count} rows extracted."
        if report:
            msg += f" Accuracy: {report.percent} ({report.grade_label})"
        self._footer_status.configure(text=msg)
        self.app.show_page("preview")

    def _on_error(self, msg: str) -> None:
        self._save_btn.configure(state="normal", text="Save Patterns & Process PDF →")
        self._footer_status.configure(text=f"Error: {msg}",
                                       text_color=("#dc2626", "#ef4444"))
        messagebox.showerror("Error", msg)
