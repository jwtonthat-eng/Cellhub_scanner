"""
Gemini Portal page: guides the user through the manual Gemini workflow.

Workflow:
  1. Show a structured prompt for the user to copy.
  2. User opens Gemini web chat, uploads PDF, pastes the prompt.
  3. User copies Gemini's JSON response back into the paste area here.
  4. App parses the response and navigates to PatternEditorPage.
"""
from __future__ import annotations

import webbrowser
from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from patterns.pattern_manager import PatternManager

if TYPE_CHECKING:
    from ui.app_window import AppWindow

GEMINI_URL = "https://gemini.google.com/app"

PROMPT_TEMPLATE = """\
Analyze the attached telecom/phone bill PDF and return ONLY a JSON object in this exact format.
Do not include any text before or after the JSON.

{
  "bill_type": "<snake_case_identifier e.g. vodacom_monthly>",
  "display_name": "<Human readable name e.g. Vodacom Monthly Bill>",
  "detection_keywords": ["<3-8 keywords unique to this carrier/bill type>"],
  "min_keyword_score": 2,
  "row_split_pattern": "<Python regex that identifies the START of each table row>",
  "columns": [
    {
      "name": "<snake_case_column_name>",
      "display_name": "<Human readable label>",
      "regex": "<Python regex using numbered capture groups>",
      "capture_group": 1,
      "default_value": "",
      "dtype": "<str|float|int|date>",
      "date_format": "<strptime format string or null>",
      "transform": "<strip|remove_commas|upper|lower|null>",
      "description": "<One sentence describing what this column captures>",
      "example_match": "<Example value from this specific document>"
    }
  ],
  "sample_rows": [
    { "<column_name>": "<actual value from the document>", ... },
    { "<column_name>": "<actual value from the document>", ... },
    { "<column_name>": "<actual value from the document>", ... }
  ]
}

RULES:
- All regex must be valid Python re module syntax.
- Use numbered capture groups (group 1, 2, ...) — NOT named groups.
- row_split_pattern should match the start of each line-item row (e.g. a date or item number).
- sample_rows must contain 3-5 REAL rows from this document — these will be used for accuracy testing.
- Focus on the main transaction/line-item table, not totals or summary sections.
"""


class GeminiPortalPage(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, app: "AppWindow") -> None:
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._pm = PatternManager()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Scrollable container
        scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=16)
        scroll_frame.grid_columnconfigure(0, weight=1)

        # ── Title ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            scroll_frame,
            text="Unrecognised Bill Type — Gemini Portal",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ctk.CTkLabel(
            scroll_frame,
            text=(
                "This bill type has no existing regex patterns. "
                "Follow the steps below to generate patterns using Gemini."
            ),
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray65"),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 20))

        # ── Step 1 ───────────────────────────────────────────────────────
        self._step_card(
            scroll_frame, row=2,
            step="Step 1",
            title="Open Gemini and upload your PDF",
            body=(
                "Click the button below to open Google Gemini in your browser.\n"
                "In Gemini, click the '+' button and upload your PDF bill."
            ),
            action_label="Open Gemini →",
            action_cmd=lambda: webbrowser.open(GEMINI_URL),
        )

        # ── Step 2 ───────────────────────────────────────────────────────
        self._step_card(
            scroll_frame, row=3,
            step="Step 2",
            title="Copy this prompt and send it to Gemini",
            body="After uploading the PDF, paste the following prompt into Gemini's message box:",
        )

        # Prompt text box
        prompt_frame = ctk.CTkFrame(scroll_frame)
        prompt_frame.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        prompt_frame.grid_columnconfigure(0, weight=1)

        self._prompt_box = ctk.CTkTextbox(
            prompt_frame,
            height=280,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="none",
        )
        self._prompt_box.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self._prompt_box.insert("1.0", PROMPT_TEMPLATE)
        self._prompt_box.configure(state="disabled")

        ctk.CTkButton(
            prompt_frame,
            text="Copy Prompt",
            width=130,
            command=self._copy_prompt,
        ).grid(row=1, column=0, sticky="e", padx=12, pady=(0, 12))

        # ── Step 3 ───────────────────────────────────────────────────────
        self._step_card(
            scroll_frame, row=5,
            step="Step 3",
            title="Paste Gemini's JSON response below",
            body=(
                "Gemini will reply with a JSON object. Copy the entire response "
                "(including the curly braces) and paste it below."
            ),
        )

        self._response_box = ctk.CTkTextbox(
            scroll_frame,
            height=200,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="none",
        )
        self._response_box.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        self._response_box.insert("1.0", "Paste Gemini response here...")

        # Clear hint on first focus
        self._response_box.bind("<FocusIn>", self._clear_hint)

        # ── Parse button ─────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        btn_row.grid(row=7, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="← Back to Upload",
            width=140,
            fg_color="transparent",
            border_width=1,
            command=lambda: self.app.show_page("upload"),
        ).pack(side="left")

        self._parse_btn = ctk.CTkButton(
            btn_row,
            text="Parse Response & Continue →",
            width=220,
            command=self._parse_response,
        )
        self._parse_btn.pack(side="right")

        self._error_label = ctk.CTkLabel(
            scroll_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("#dc2626", "#ef4444"),
            wraplength=700,
            justify="left",
        )
        self._error_label.grid(row=8, column=0, sticky="w", pady=(0, 20))

    # ------------------------------------------------------------------
    # Step card helper
    # ------------------------------------------------------------------

    def _step_card(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        step: str,
        title: str,
        body: str,
        action_label: str | None = None,
        action_cmd=None,
    ) -> None:
        card = ctk.CTkFrame(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(1, weight=1)

        # Step badge
        badge = ctk.CTkLabel(
            card,
            text=step,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=("#2563EB", "#3B82F6"),
            text_color="white",
            corner_radius=6,
            width=60,
            height=24,
        )
        badge.grid(row=0, column=0, padx=(14, 10), pady=(14, 4), sticky="nw")

        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(14, 2))

        ctk.CTkLabel(
            card,
            text=body,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70"),
            anchor="w",
            justify="left",
            wraplength=580,
        ).grid(row=1, column=1, sticky="w", pady=(0, 4), padx=(0, 12))

        if action_label and action_cmd:
            ctk.CTkButton(
                card,
                text=action_label,
                width=150,
                command=action_cmd,
            ).grid(row=2, column=1, sticky="w", pady=(4, 14))
        else:
            ctk.CTkFrame(card, height=14, fg_color="transparent").grid(row=2, column=1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _copy_prompt(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(PROMPT_TEMPLATE)
        self.update()

    def _clear_hint(self, _event) -> None:
        current = self._response_box.get("1.0", "end-1c")
        if current.strip() == "Paste Gemini response here...":
            self._response_box.delete("1.0", "end")

    def _parse_response(self) -> None:
        raw_text = self._response_box.get("1.0", "end-1c").strip()
        if not raw_text or raw_text == "Paste Gemini response here...":
            self._set_error("Please paste Gemini's response before continuing.")
            return

        try:
            raw_dict = PatternManager.parse_gemini_response(raw_text)
        except ValueError as exc:
            self._set_error(f"Could not parse JSON: {exc}")
            return

        # Store sample_rows in app state before passing to editor
        self.app.state["sample_rows"] = raw_dict.get("sample_rows", [])

        self._set_error("")
        self.app.show_pattern_editor(raw_dict)

    def _set_error(self, msg: str) -> None:
        self._error_label.configure(text=msg)

    def on_show(self) -> None:
        # Reset response box when shown fresh
        self._response_box.delete("1.0", "end")
        self._response_box.insert("1.0", "Paste Gemini response here...")
        self._set_error("")
