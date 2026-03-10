"""
Google Drive client: OAuth2 authentication and file upload.
Uses google-api-python-client with a cached token for seamless re-auth.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    return base / relative


DEFAULT_CREDENTIALS_PATH = _resource_path("config/credentials/client_secret.json")
DEFAULT_TOKEN_PATH = _resource_path("config/token.json")


@dataclass
class DriveFolder:
    id: str
    name: str
    parent_id: str | None = None


class DriveClient:
    def __init__(
        self,
        credentials_path: str | Path | None = None,
        token_path: str | Path | None = None,
    ) -> None:
        self._creds_path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
        self._token_path = Path(token_path) if token_path else DEFAULT_TOKEN_PATH
        self._service = None
        self._creds = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def is_credentials_available(self) -> bool:
        return self._creds_path.exists()

    def is_authenticated(self) -> bool:
        if self._creds is None:
            return False
        return self._creds.valid

    def authenticate(self) -> None:
        """
        Load cached token or run OAuth2 browser flow.
        Saves refreshed token to token_path.
        Raises FileNotFoundError if credentials JSON is missing.
        Raises RuntimeError if authentication fails.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ImportError(
                "Google API libraries are not installed. "
                "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
            ) from exc

        if not self._creds_path.exists():
            raise FileNotFoundError(
                f"Google OAuth credentials not found at: {self._creds_path}\n"
                "Please download your OAuth2 client JSON from Google Cloud Console "
                "and save it to config/credentials/client_secret.json"
            )

        creds = None

        # Load cached token
        if self._token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self._token_path), SCOPES)
            except Exception:
                creds = None

        # Refresh or re-authenticate
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._creds_path), SCOPES)
            try:
                creds = flow.run_local_server(port=0, open_browser=True)
            except OSError:
                # Fallback: console-based auth
                creds = flow.run_console()

        # Save token
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._token_path, "w") as fh:
            fh.write(creds.to_json())

        self._creds = creds
        self._service = build("drive", "v3", credentials=creds)
        logger.info("Google Drive authentication successful")

    def ensure_authenticated(self) -> None:
        if not self.is_authenticated():
            self.authenticate()

    # ------------------------------------------------------------------
    # Folder listing
    # ------------------------------------------------------------------

    def list_folders(self, parent_id: str = "root") -> list[DriveFolder]:
        """Return immediate child folders of parent_id."""
        self.ensure_authenticated()
        query = (
            f"'{parent_id}' in parents "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        result = (
            self._service.files()
            .list(q=query, fields="files(id, name, parents)", pageSize=100)
            .execute()
        )
        folders = []
        for f in result.get("files", []):
            folders.append(DriveFolder(
                id=f["id"],
                name=f["name"],
                parent_id=(f.get("parents") or [None])[0],
            ))
        return sorted(folders, key=lambda f: f.name.lower())

    # ------------------------------------------------------------------
    # File upload
    # ------------------------------------------------------------------

    def upload_file(
        self,
        local_path: str | Path,
        drive_folder_id: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        """
        Upload a file to the specified Drive folder.

        Args:
            local_path: Local file path to upload.
            drive_folder_id: Drive folder ID to upload into.
            progress_callback: Optional (bytes_uploaded, total_bytes) callback.

        Returns:
            The Drive file ID of the uploaded file.
        """
        from googleapiclient.http import MediaFileUpload

        self.ensure_authenticated()

        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        file_size = local_path.stat().st_size
        mime_type = _mime_for(local_path.suffix.lower())

        file_metadata = {
            "name": local_path.name,
            "parents": [drive_folder_id],
        }
        media = MediaFileUpload(
            str(local_path),
            mimetype=mime_type,
            resumable=True,
            chunksize=1024 * 1024,  # 1 MB chunks
        )

        request = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                uploaded = int(status.resumable_progress)
                progress_callback(uploaded, file_size)

        if progress_callback:
            progress_callback(file_size, file_size)

        file_id: str = response.get("id", "")
        logger.info("Uploaded %s → Drive file ID: %s", local_path.name, file_id)
        return file_id

    def get_file_url(self, file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mime_for(suffix: str) -> str:
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
    }.get(suffix, "application/octet-stream")
