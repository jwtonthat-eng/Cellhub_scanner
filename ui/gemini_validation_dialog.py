"""
Gemini Validation Dialog — optional accuracy check for already-recognised bill types.

Workflow:
  1. Show a prompt asking Gemini to extract 3-5 sample rows from the bill.
  2. User pastes Gemini's JSON response.
  3. App extracts sample_rows, runs AccuracyScorer against the extracted DataFrame.
  4. Displays per-column accuracy and overall score.
  5. Stores the report in app state so PreviewPage shows the badge.
"""
from __future__ import annotations

import json
import re
import webbrowser
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from core.accuracy_scorer import AccuracyScorer
from patterns.pattern_manager import PatternManager

if TYPE_CHECKING:
    from ui.app_window import AppWindow

GEMINI_URL = "https://gemini.google.com/app"

# Prompt asks only for sample rows — no full pattern generation needed
VALIDATION_PROMPT_TEMPLATE = """\
I have a telecom/phone bill PDF attached. I need you to manually extract \
3 to 5 rows from the main transaction/line-item table and return them as JSON.

Return ONLY a JSON object in this exact format — no other text:

{{
  "sample_rows": [
    {{ "column_name": "value", "column_name": "value", ... }},
    {{ "column_name": "value", "column_name": "value", ... }},
    {{ "column_name": "value", "column_name": "value", ... }}
  ]
}}

Column names to use: {column_names}

Rules:
- Use the exact column names listed above.
- Copy values exactly as they appear in the PDF (dates, amounts, descriptions).
- For amounts, include the numeric value only (e.g. "129.00" not "R 129.00").
- Pick rows from different parts of the document (beginning, middle, end).
- Return ONLY valid JSON starting with {{ and ending with }}.
"""

COLOR_MAP = {
    "green": ("#16a34a", "#22c55e"),
    "yellow": ("#ca8a04", "#eab308"),
    "orange": ("#ea580c", "#f97316"),
    "red": ("#dc2626", "#ef4444"),
}


class GeminiValidationDialog(ctk.CTkToplevel):
    def __init__(self, parent, app: "AppWindow") -> None:
        super().__init__(parent)
        self.app = app
        self.title("Validate Accuracy with Gemini")
        self.geometry("640x720")
        self.resizable(True, True)
        self.minsize(540, 580)

        schema = app.state.get("schema")
        self._column_names = (
            ", ".join(c.name for c in schema.columns) if schema else "date, description, amount"
        )
        self._schema = schema
        self._scored = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            scroll,
            text="Optional: Validate Extraction Accuracy",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            scroll,
            text=(
                "Ask Gemini to manually pick a few rows from your bill. "
                "The app will compare them to the extracted data and show an accuracy score."
            ),
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
            wraplength=580,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 20))

        # Step 1
        self._step_card(scroll, row=2,
            step="Step 1",
            title="Open Gemini and upload your PDF",
            body="Click to open Google Gemini, then upload the same PDF bill.",
            btn_text="Open Gemini →",
            btn_cmd=lambda: webbrowser.open(GEMINI_URL),
        )

        # Step 2 — prompt
        self._step_card(scroll, row=3,
            step="Step 2",
            title="Copy this prompt and send it with your PDF",
            body="Paste the prompt below into Gemini's chat along with your uploaded PDF:",
        )

        prompt_frame = ctk.CTkFrame(scroll)
        prompt_frame.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        prompt_frame.grid_columnconfigure(0, weight=1)

        self._prompt_box = ctk.CTkTextbox(
            prompt_frame,
            height=180,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word",
        )
        self._prompt_box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        prompt_text = VALIDATION_PROMPT_TEMPLATE.format(column_names=self._column_names)
        self._prompt_box.insert("1.0", prompt_text)
        self._prompt_box.configure(state="disabled")

        ctk.CTkButton(
            prompt_frame,
            text="Copy Prompt",
            width=120,
            height=36,
            command=self._copy_prompt,
        ).grid(row=1, column=0, sticky="e", padx=12, pady=(0, 12))

        # Step 3 — paste response
        self._step_card(scroll, row=5,
            step="Step 3",
            title="Paste Gemini's response below",
            body='Copy Gemini\'s full reply (the JSON with "sample_rows") and paste it here:',
        )

        self._response_box = ctk.CTkTextbox(
            scroll,
            height=150,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="none",
        )
        self._response_box.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        self._response_box.insert("1.0", "Paste Gemini's JSON response here...")
        self._response_box.bind("<FocusIn>", self._clear_hint)

        # Score button
        self._score_btn = ctk.CTkButton(
            scroll,
            text="Run Accuracy Check →",
            height=48,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run_score,
        )
        self._score_btn.grid(row=7, column=0, sticky="ew", pady=(0, 8))

        self._error_label = ctk.CTkLabel(
            scroll,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("#dc2626", "#ef4444"),
            wraplength=580,
            justify="left",
        )
        self._error_label.grid(row=8, column=0, sticky="w", pady=(0, 8))

        # Results panel (hidden until scored)
        self._results_frame = ctk.CTkFrame(scroll)
        self._results_frame.grid_columnconfigure(0, weight=1)
        # Don't grid it yet — shown after scoring

        # Close button (bottom, always visible)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

        ctk.CTkButton(
            footer,
            text="Close",
            width=120,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="left")

        self._done_btn = ctk.CTkButton(
            footer,
            text="Done — View Results",
            width=180,
            state="disabled",
            command=self._finish,
        )
        self._done_btn.pack(side="right")

    # ------------------------------------------------------------------
    # Step card helper
    # ------------------------------------------------------------------

    def _step_card(self, parent, row: int, step: str, title: str, body: str,
                   btn_text: str | None = None, btn_cmd=None) -> None:
        card = ctk.CTkFrame(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=step,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#2563EB", "#3B82F6"),
            text_color="white",
            corner_radius=6, width=60, height=24,
        ).grid(row=0, column=0, padx=(14, 10), pady=(14, 4), sticky="nw")

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(14, 2))

        ctk.CTkLabel(
            card, text=body,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70"),
            anchor="w", justify="left", wraplength=500,
        ).grid(row=1, column=1, sticky="w", pady=(0, 4), padx=(0, 12))

        if btn_text and btn_cmd:
            ctk.CTkButton(
                card, text=btn_text, width=150, height=36, command=btn_cmd,
            ).grid(row=2, column=1, sticky="w", pady=(4, 14))
        else:
            ctk.CTkFrame(card, height=14, fg_color="transparent").grid(row=2, column=1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _copy_prompt(self) -> None:
        prompt_text = VALIDATION_PROMPT_TEMPLATE.format(column_names=self._column_names)
        self.clipboard_clear()
        self.clipboard_append(prompt_text)
        self.update()

    def _clear_hint(self, _event) -> None:
        if self._response_box.get("1.0", "end-1c").strip() == "Paste Gemini's JSON response here...":
            self._response_box.delete("1.0", "end")

    def _run_score(self) -> None:
        raw_text = self._response_box.get("1.0", "end-1c").strip()
        if not raw_text or "Paste Gemini" in raw_text:
            self._set_error("Please paste Gemini's response before running the check.")
            return

        # Parse — accept either full bill JSON or just {"sample_rows": [...]}
        try:
            parsed = PatternManager.parse_gemini_response(raw_text)
        except ValueError as exc:
            self._set_error(f"Could not parse JSON: {exc}")
            return

        sample_rows = parsed.get("sample_rows")
        if not sample_rows:
            self._set_error(
                'No "sample_rows" key found in the response. '
                "Make sure Gemini followed the prompt format.")
            return

        df = self.app.state.get("dataframe")
        if df is None or df.empty:
            self._set_error("No extracted data available. Process a PDF first.")
            return

        dtypes = {}
        if self._schema:
            dtypes = {col.name: col.dtype for col in self._schema.columns}

        scorer = AccuracyScorer()
        report = scorer.score(sample_rows, df, column_dtypes=dtypes)

        # Store in app state
        self.app.state["accuracy_report"] = report
        self.app.state["sample_rows"] = sample_rows

        self._set_error("")
        self._show_results(report)

    def _show_results(self, report) -> None:
        # Clear and rebuild results frame
        for w in self._results_frame.winfo_children():
            w.destroy()

        self._results_frame.grid(row=9, column=0, sticky="ew",
                                  in_=self._response_box.master if hasattr(self._response_box, 'master') else self)

        # Overall score banner
        colors = COLOR_MAP.get(report.color_grade, COLOR_MAP["red"])
        banner = ctk.CTkFrame(
            self._results_frame,
            fg_color=colors[0],
            corner_radius=10,
        )
        banner.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 12))
        banner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            banner,
            text=f"{report.grade_label}",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white",
        ).grid(row=0, column=0, padx=20, pady=16)

        ctk.CTkLabel(
            banner,
            text=f"{report.percent} overall accuracy\n"
                 f"{report.aligned_pairs} of {report.total_sample} sample rows matched",
            font=ctk.CTkFont(size=12),
            text_color="white",
            justify="left",
        ).grid(row=0, column=1, sticky="w", pady=16)

        # Per-column breakdown
        ctk.CTkLabel(
            self._results_frame,
            text="Per-column accuracy:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))

        for i, cs in enumerate(report.per_column, start=2):
            col_colors = COLOR_MAP.get(cs.color, COLOR_MAP["red"])
            row_f = ctk.CTkFrame(self._results_frame, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", pady=2)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row_f,
                text=cs.column_name,
                font=ctk.CTkFont(size=11),
                width=120,
                anchor="w",
            ).grid(row=0, column=0, sticky="w")

            bar_bg = ctk.CTkFrame(row_f, height=18, corner_radius=4,
                                   fg_color=("gray80", "gray30"))
            bar_bg.grid(row=0, column=1, sticky="ew", padx=(8, 8))
            bar_bg.grid_propagate(False)
            bar_bg.grid_columnconfigure(0, weight=1)

            fill_w = max(4, int(cs.score * 200))
            ctk.CTkFrame(
                bar_bg,
                width=fill_w,
                height=18,
                corner_radius=4,
                fg_color=col_colors[0],
            ).place(x=0, y=0)

            ctk.CTkLabel(
                row_f,
                text=f"{cs.score * 100:.0f}%  ({cs.matched}/{cs.total})",
                font=ctk.CTkFont(size=11),
                text_color=col_colors,
                width=80,
                anchor="e",
            ).grid(row=0, column=2, sticky="e")

        # Grid the results into scroll frame
        scroll_children = list(self._results_frame.master.winfo_children()
                               if hasattr(self._results_frame, 'master') else [])

        # Re-grid results frame into the scrollable area
        self._results_frame.grid(row=9, column=0, sticky="ew", pady=(8, 0))

        self._scored = True
        self._done_btn.configure(state="normal")

    def _finish(self) -> None:
        self.destroy()
        self.app.show_page("preview")

    def _set_error(self, msg: str) -> None:
        self._error_label.configure(text=msg)
