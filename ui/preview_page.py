"""
Preview page: scrollable table view of the extracted DataFrame.
Shows accuracy badge for newly-created bill types.
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk
import pandas as pd

if TYPE_CHECKING:
    from ui.app_window import AppWindow

COLOR_MAP = {
    "green": ("#16a34a", "#22c55e"),
    "yellow": ("#ca8a04", "#eab308"),
    "orange": ("#ea580c", "#f97316"),
    "red": ("#dc2626", "#ef4444"),
}


class PreviewPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, app: "AppWindow") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Extracted Table Preview",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        # Info labels (bill type, rows, accuracy)
        self._info_frame = ctk.CTkFrame(header, fg_color="transparent")
        self._info_frame.grid(row=0, column=2, sticky="e")

        self._bill_type_label = ctk.CTkLabel(
            self._info_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._bill_type_label.pack(side="right", padx=8)

        self._accuracy_badge = ctk.CTkLabel(
            self._info_frame,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
            width=100,
        )
        self._accuracy_badge.pack(side="right", padx=4)

        # Table container with scrollbars
        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        # Use tk.Text as a table (simpler than ttk.Treeview theming)
        # We use a Canvas + Frame approach for the scrollable table
        self._canvas = tk.Canvas(table_frame, highlightthickness=0, bg="#1a1a1a")
        self._canvas.grid(row=0, column=0, sticky="nsew")

        v_scroll = ctk.CTkScrollbar(table_frame, command=self._canvas.yview)
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll = ctk.CTkScrollbar(
            table_frame, orientation="horizontal", command=self._canvas.xview)
        h_scroll.grid(row=1, column=0, sticky="ew")

        self._canvas.configure(
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )

        self._table_inner = tk.Frame(self._canvas, bg="#1a1a1a")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._table_inner, anchor="nw")

        self._table_inner.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel scrolling
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Bottom bar
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))

        self._row_count_label = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._row_count_label.pack(side="left")

        ctk.CTkButton(
            bottom,
            text="Export →",
            width=120,
            command=lambda: self.app.show_page("export"),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        df: pd.DataFrame | None = self.app.state.get("dataframe")
        schema = self.app.state.get("schema")
        report = self.app.state.get("accuracy_report")

        if df is None or df.empty:
            self._clear_table()
            self._bill_type_label.configure(text="No data loaded")
            return

        display_name = schema.display_name if schema else "Unknown"
        self._bill_type_label.configure(text=f"Bill type: {display_name}")
        self._row_count_label.configure(text=f"{len(df)} rows × {len(df.columns)} columns")

        # Show accuracy badge if available
        if report:
            colors = COLOR_MAP.get(report.color_grade, COLOR_MAP["red"])
            self._accuracy_badge.configure(
                text=f"{report.grade_label} {report.percent}",
                fg_color=colors[0],
                text_color="white",
            )
        else:
            self._accuracy_badge.configure(text="", fg_color="transparent")

        self._render_table(df)

    def _clear_table(self) -> None:
        for widget in self._table_inner.winfo_children():
            widget.destroy()

    def _render_table(self, df: pd.DataFrame) -> None:
        self._clear_table()
        mode = ctk.get_appearance_mode()
        header_bg = "#1F4E79" if mode == "Dark" else "#2563EB"
        header_fg = "#FFFFFF"
        row_bg_even = "#1e1e1e" if mode == "Dark" else "#f0f4f8"
        row_bg_odd = "#262626" if mode == "Dark" else "#ffffff"
        row_fg = "#e5e7eb" if mode == "Dark" else "#111827"
        border_color = "#374151" if mode == "Dark" else "#d1d5db"

        col_widths = []
        for col in df.columns:
            col_data_str = df[col].astype(str)
            max_len = max(len(str(col)), col_data_str.str.len().max() if not df.empty else 0)
            col_widths.append(min(max_len * 8 + 16, 300))

        # Header row
        for j, (col, w) in enumerate(zip(df.columns, col_widths)):
            tk.Label(
                self._table_inner,
                text=str(col),
                font=("Segoe UI", 9, "bold"),
                bg=header_bg, fg=header_fg,
                width=w // 7,
                anchor="w",
                padx=6, pady=4,
                relief="flat",
            ).grid(row=0, column=j, padx=(0, 1), pady=(0, 1), sticky="ew")

        # Data rows (cap at 500 for performance)
        max_rows = min(len(df), 500)
        for i, row_data in enumerate(df.head(max_rows).itertuples(index=False), start=1):
            bg = row_bg_even if i % 2 == 0 else row_bg_odd
            for j, (val, w) in enumerate(zip(row_data, col_widths)):
                display = "" if (not isinstance(val, str) and pd.isna(val)) else str(val)
                tk.Label(
                    self._table_inner,
                    text=display,
                    font=("Segoe UI", 9),
                    bg=bg, fg=row_fg,
                    width=w // 7,
                    anchor="w",
                    padx=6, pady=3,
                    relief="flat",
                ).grid(row=i, column=j, padx=(0, 1), pady=(0, 1), sticky="ew")

        if len(df) > 500:
            tk.Label(
                self._table_inner,
                text=f"... {len(df) - 500} more rows (showing first 500)",
                font=("Segoe UI", 9, "italic"),
                bg=row_bg_even, fg="#6b7280",
                padx=6, pady=4,
            ).grid(row=max_rows + 1, column=0, columnspan=len(df.columns), sticky="ew")

    # ------------------------------------------------------------------
    # Scroll helpers
    # ------------------------------------------------------------------

    def _on_frame_configure(self, _event: tk.Event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
