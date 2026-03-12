"""
Main application window: sidebar navigation + page switcher.
All pages are created once and shown/hidden via pack/pack_forget.
"""
from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    pass


def _resource_path(relative: str) -> Path:
    """Return absolute path — works both in source tree and PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


# Configure appearance
ctk.set_appearance_mode("dark")
_theme_path = _resource_path("assets/tmobile_theme.json")
if _theme_path.exists():
    ctk.set_default_color_theme(str(_theme_path))
else:
    ctk.set_default_color_theme("blue")

SIDEBAR_WIDTH = 220          # Wider for touch targets
APP_TITLE = "Cellhub Scanner"
APP_GEOMETRY = "1280x800"   # Surface tablet default resolution

# Navigation items: (label, page_key)
NAV_ITEMS = [
    ("Upload PDF", "upload"),
    ("Preview Table", "preview"),
    ("Export", "export"),
    ("Pattern Manager", "patterns"),
    ("Bill Audit", "audit"),
]


class AppWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_GEOMETRY)
        self.minsize(960, 640)
        # Surface tablet: maximise on startup for best touch experience
        try:
            self.state("zoomed")
        except Exception:
            pass

        # Shared application state passed between pages
        self.state: dict = {
            "pdf_path": None,
            "bill_type": None,
            "schema": None,
            "dataframe": None,
            "accuracy_report": None,
            "sample_rows": None,
            "export_path": None,
            # Audit session state
            "audit_report": None,
            "audit_dfs": None,
            "audit_labels": None,
        }

        self._build_layout()
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._active_page: str = ""

        self._register_pages()
        self.show_page("upload")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._sidebar = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_rowconfigure(10, weight=1)

        # Logo / title area
        logo_label = ctk.CTkLabel(
            self._sidebar,
            text=APP_TITLE,
            font=ctk.CTkFont(size=19, weight="bold"),
        )
        logo_label.grid(row=0, column=0, padx=16, pady=(24, 6))

        subtitle = ctk.CTkLabel(
            self._sidebar,
            text="Telecom Bill Processor",
            font=ctk.CTkFont(size=12),
            text_color=("gray60", "gray45"),
        )
        subtitle.grid(row=1, column=0, padx=16, pady=(0, 16))

        ctk.CTkFrame(self._sidebar, height=1, fg_color=("gray80", "gray30")).grid(
            row=2, column=0, sticky="ew", padx=8, pady=4)

        # Nav buttons — large touch targets (height=46)
        for i, (label, key) in enumerate(NAV_ITEMS, start=3):
            btn = ctk.CTkButton(
                self._sidebar,
                text=label,
                anchor="w",
                corner_radius=8,
                height=46,
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray25"),
                command=lambda k=key: self.show_page(k),
            )
            btn.grid(row=i, column=0, padx=8, pady=4, sticky="ew")
            self._nav_buttons[key] = btn

        # Help button
        self._help_btn = ctk.CTkButton(
            self._sidebar,
            text="? Help Guide",
            height=40,
            fg_color="transparent",
            text_color=("gray40", "gray60"),
            hover_color=("gray85", "gray20"),
            command=self._open_help,
        )
        self._help_btn.grid(row=19, column=0, padx=8, pady=(4, 2), sticky="ew")

        # Theme toggle at bottom
        self._theme_btn = ctk.CTkButton(
            self._sidebar,
            text="Toggle Theme",
            height=40,
            fg_color="transparent",
            text_color=("gray40", "gray60"),
            hover_color=("gray85", "gray20"),
            command=self._toggle_theme,
        )
        self._theme_btn.grid(row=20, column=0, padx=8, pady=(2, 20), sticky="ew")

        # Main content area
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray95", "gray10"))
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Page registration
    # ------------------------------------------------------------------

    def _register_pages(self) -> None:
        from ui.upload_page import UploadPage
        from ui.preview_page import PreviewPage
        from ui.export_page import ExportPage
        from ui.pattern_list_page import PatternListPage
        from ui.audit_session_page import AuditSessionPage
        from ui.audit_results_page import AuditResultsPage

        page_classes = {
            "upload":        UploadPage,
            "preview":       PreviewPage,
            "export":        ExportPage,
            "patterns":      PatternListPage,
            "audit":         AuditSessionPage,
            "audit_results": AuditResultsPage,
        }
        for key, cls in page_classes.items():
            page = cls(self._content, app=self)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = page

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        if self._active_page == key:
            return

        # Deactivate current
        if self._active_page and self._active_page in self._nav_buttons:
            self._nav_buttons[self._active_page].configure(
                fg_color="transparent",
                text_color=("gray10", "gray90"),
            )

        # Activate new
        self._active_page = key
        self._pages[key].tkraise()
        if key in self._nav_buttons:
            self._nav_buttons[key].configure(
                fg_color=("gray70", "gray30"),
                text_color=("gray5", "white"),
            )

        # Notify page it's being shown
        page = self._pages[key]
        if hasattr(page, "on_show"):
            page.on_show()

    def show_audit_results(self) -> None:
        """Navigate to the audit results page (created at startup, refreshes on show)."""
        self._active_page = ""
        self.show_page("audit_results")

    def show_gemini_portal(self) -> None:
        """Lazily create and show the Gemini portal page."""
        if "gemini" not in self._pages:
            from ui.gemini_portal_page import GeminiPortalPage
            page = GeminiPortalPage(self._content, app=self)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages["gemini"] = page
        self._active_page = ""
        self.show_page("gemini")

    def show_pattern_editor(self, raw_dict: dict) -> None:
        """Lazily create and show the PatternEditorPage with fresh data."""
        from ui.pattern_editor_page import PatternEditorPage
        # Always recreate to load fresh data
        if "editor" in self._pages:
            self._pages["editor"].destroy()
        page = PatternEditorPage(self._content, app=self, raw_dict=raw_dict)
        page.grid(row=0, column=0, sticky="nsew")
        self._pages["editor"] = page
        self._active_page = ""
        self.show_page("editor")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _open_help(self) -> None:
        guide = _resource_path("docs/user_guide.html")
        webbrowser.open(guide.as_uri())

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        ctk.set_appearance_mode("light" if current == "Dark" else "dark")
