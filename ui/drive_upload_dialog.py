"""
Google Drive upload dialog: folder picker tree + upload progress.
Shows setup instructions if credentials are not configured.
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from integrations.drive_client import DriveClient, DriveFolder

if TYPE_CHECKING:
    pass


class DriveUploadDialog(ctk.CTkToplevel):
    def __init__(self, parent, file_path: str) -> None:
        super().__init__(parent)
        self.title("Upload to Google Drive")
        self.geometry("560x600")
        self.resizable(False, False)
        self._file_path = file_path
        self._client = DriveClient()
        self._selected_folder_id: str = "root"
        self._selected_folder_name: str = "My Drive (root)"
        self._folder_cache: dict[str, list[DriveFolder]] = {}

        self._build_ui()
        self._initialize()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text="Upload to Google Drive",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 4))

        file_name = Path(self._file_path).name
        ctk.CTkLabel(
            self,
            text=f"File: {file_name}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))

        # Folder picker
        folder_frame = ctk.CTkFrame(self)
        folder_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))
        folder_frame.grid_columnconfigure(0, weight=1)
        folder_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            folder_frame,
            text="Select destination folder",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        # Treeview using tkinter
        tree_container = tk.Frame(folder_frame, bg="#1a1a1a")
        tree_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        self._tree = tk.ttk.Treeview(
            tree_container,
            selectmode="browse",
            show="tree headings",
            height=12,
        )
        self._tree.heading("#0", text="Google Drive Folders")
        self._tree.column("#0", minwidth=200)

        v_scroll = tk.ttk.Scrollbar(
            tree_container, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=v_scroll.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Selected folder label
        self._selection_label = ctk.CTkLabel(
            self,
            text=f"Destination: {self._selected_folder_name}",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._selection_label.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 8))

        # Progress bar
        self._progress = ctk.CTkProgressBar(self, width=520)
        self._progress.set(0)
        self._progress.grid(row=4, column=0, padx=20, pady=(0, 8))

        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
        )
        self._status_label.grid(row=5, column=0, padx=20, pady=(0, 8))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            width=110,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="left")

        self._upload_btn = ctk.CTkButton(
            btn_row,
            text="Upload",
            width=130,
            command=self._start_upload,
        )
        self._upload_btn.pack(side="right")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        # Import ttk after window exists
        import tkinter.ttk  # noqa: F401

        if not self._client.is_credentials_available():
            self._show_setup_instructions()
            return

        self._set_status("Authenticating with Google Drive...")
        threading.Thread(target=self._auth_and_load, daemon=True).start()

    def _auth_and_load(self) -> None:
        try:
            self._client.authenticate()
            folders = self._client.list_folders("root")
            self.after(0, self._populate_tree, folders)
            self.after(0, lambda: self._set_status(""))
        except Exception as exc:
            self.after(0, lambda: self._set_status(f"Auth error: {exc}"))

    # ------------------------------------------------------------------
    # Setup instructions (shown when credentials.json is missing)
    # ------------------------------------------------------------------

    def _show_setup_instructions(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        self.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(self)
        scroll.grid(row=0, column=0, sticky="nsew", padx=20, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            scroll,
            text="Google Drive Setup Required",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))

        steps = [
            "1. Go to console.cloud.google.com",
            "2. Create a project (or select an existing one)",
            "3. Enable the 'Google Drive API' under APIs & Services → Library",
            "4. Go to APIs & Services → Credentials",
            "5. Click 'Create Credentials' → OAuth 2.0 Client IDs",
            "6. Choose 'Desktop application' as the app type",
            "7. Download the JSON file",
            "8. Save it to:  config/credentials/client_secret.json",
            "9. Relaunch the app and try again",
        ]
        for step in steps:
            ctk.CTkLabel(
                scroll,
                text=step,
                font=ctk.CTkFont(size=11),
                anchor="w",
                justify="left",
            ).pack(anchor="w", pady=2)

        ctk.CTkButton(
            scroll,
            text="Close",
            command=self.destroy,
        ).pack(pady=(20, 0))

    # ------------------------------------------------------------------
    # Folder tree
    # ------------------------------------------------------------------

    def _populate_tree(self, folders: list[DriveFolder]) -> None:
        # Root node
        self._tree.insert("", "end", iid="root", text="📁 My Drive", open=True)
        for f in folders:
            self._tree.insert(
                "root", "end",
                iid=f.id,
                text=f"📁 {f.name}",
                values=(f.id,),
                tags=("folder",),
            )
            # Insert dummy child so the folder shows as expandable
            self._tree.insert(f.id, "end", iid=f"{f.id}__dummy", text="Loading...")

    def _on_tree_open(self, event: tk.Event) -> None:
        item = self._tree.focus()
        if item == "root":
            return
        # Remove dummy, load real children
        children = self._tree.get_children(item)
        if len(children) == 1 and children[0].endswith("__dummy"):
            self._tree.delete(children[0])
            threading.Thread(
                target=self._load_subfolders,
                args=(item,),
                daemon=True,
            ).start()

    def _load_subfolders(self, parent_id: str) -> None:
        try:
            folders = self._client.list_folders(parent_id)
            self.after(0, self._insert_subfolders, parent_id, folders)
        except Exception as exc:
            logger_msg = f"Failed to load subfolders: {exc}"
            self.after(0, lambda: self._set_status(logger_msg))

    def _insert_subfolders(self, parent_id: str, folders: list[DriveFolder]) -> None:
        for f in folders:
            if not self._tree.exists(f.id):
                self._tree.insert(
                    parent_id, "end",
                    iid=f.id,
                    text=f"📁 {f.name}",
                    values=(f.id,),
                )
                self._tree.insert(f.id, "end", iid=f"{f.id}__dummy", text="Loading...")

    def _on_tree_select(self, event: tk.Event) -> None:
        item = self._tree.focus()
        if item == "root":
            self._selected_folder_id = "root"
            self._selected_folder_name = "My Drive (root)"
        else:
            name = self._tree.item(item, "text").replace("📁 ", "").strip()
            self._selected_folder_id = item
            self._selected_folder_name = name
        self._selection_label.configure(
            text=f"Destination: {self._selected_folder_name}")

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def _start_upload(self) -> None:
        self._upload_btn.configure(state="disabled", text="Uploading...")
        self._progress.set(0)
        threading.Thread(target=self._run_upload, daemon=True).start()

    def _run_upload(self) -> None:
        try:
            file_size = Path(self._file_path).stat().st_size

            def progress_cb(uploaded: int, total: int) -> None:
                ratio = uploaded / total if total > 0 else 0
                self.after(0, lambda: self._progress.set(ratio))
                self.after(0, lambda: self._set_status(
                    f"Uploading... {uploaded // 1024:,} KB / {total // 1024:,} KB"))

            file_id = self._client.upload_file(
                self._file_path,
                self._selected_folder_id,
                progress_callback=progress_cb,
            )
            url = self._client.get_file_url(file_id)
            self.after(0, self._on_upload_done, url)

        except Exception as exc:
            self.after(0, self._on_upload_error, str(exc))

    def _on_upload_done(self, url: str) -> None:
        self._progress.set(1.0)
        self._set_status("Upload complete!")
        self._upload_btn.configure(state="normal", text="Done")
        messagebox.showinfo(
            "Upload Complete",
            f"File uploaded successfully to Google Drive.\n\nURL:\n{url}",
        )
        self.destroy()

    def _on_upload_error(self, msg: str) -> None:
        self._upload_btn.configure(state="normal", text="Upload")
        self._set_status(f"Error: {msg}")
        messagebox.showerror("Upload Failed", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)
