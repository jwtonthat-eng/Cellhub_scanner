"""
Pattern List page: view and manage all saved bill-type regex schemas.
"""
from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from patterns.pattern_manager import PatternManager

if TYPE_CHECKING:
    from ui.app_window import AppWindow


class PatternListPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, app: "AppWindow") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._pm = PatternManager()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Saved Regex Patterns",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text=(
                "These are the bill types the app can currently recognize and process. "
                "New patterns are added via the Gemini Portal workflow."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Scrollable list
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(8, 16))
        self._scroll.grid_columnconfigure(0, weight=1)

        self._render_list()

    def _render_list(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()

        schemas = self._pm.all_schemas()
        if not schemas:
            ctk.CTkLabel(
                self._scroll,
                text="No patterns saved yet. Process an unknown bill type to create new patterns.",
                font=ctk.CTkFont(size=12),
                text_color=("gray40", "gray65"),
            ).pack(pady=40)
            return

        for i, (bill_type, schema) in enumerate(schemas.items()):
            card = ctk.CTkFrame(self._scroll)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(1, weight=1)

            # Bill type info
            ctk.CTkLabel(
                card,
                text=schema.display_name,
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 2))

            ctk.CTkLabel(
                card,
                text=f"ID: {bill_type}  |  {len(schema.columns)} column(s)  |  "
                     f"Keywords: {', '.join(schema.detection_keywords[:4])}",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray65"),
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

            # Accuracy score if available
            acc = schema.metadata.get("accuracy_score_on_creation")
            if acc is not None:
                acc_text = f"Accuracy: {acc * 100:.1f}%"
                acc_color = (
                    ("#16a34a", "#22c55e") if acc >= 0.9 else
                    ("#ca8a04", "#eab308") if acc >= 0.7 else
                    ("#ea580c", "#f97316") if acc >= 0.5 else
                    ("#dc2626", "#ef4444")
                )
                ctk.CTkLabel(
                    card,
                    text=acc_text,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=acc_color,
                ).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))

            # Column list
            col_names = ", ".join(c.name for c in schema.columns)
            ctk.CTkLabel(
                card,
                text=f"Columns: {col_names}",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray65"),
                wraplength=600,
                justify="left",
            ).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 8))

            # Delete button
            ctk.CTkButton(
                card,
                text="Delete",
                width=80,
                height=28,
                fg_color=("#dc2626", "#991b1b"),
                hover_color=("#b91c1c", "#7f1d1d"),
                command=lambda bt=bill_type: self._delete(bt),
            ).grid(row=0, column=2, padx=(0, 14), pady=(12, 2))

    def _delete(self, bill_type: str) -> None:
        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Delete pattern '{bill_type}'? This cannot be undone.",
        )
        if confirmed:
            self._pm.delete_bill_type(bill_type)
            self._render_list()

    def on_show(self) -> None:
        self._pm.load()
        self._render_list()
