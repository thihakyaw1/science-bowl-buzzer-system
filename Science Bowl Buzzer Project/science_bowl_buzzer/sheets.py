from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCOPES = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
)


@dataclass(frozen=True)
class GoogleDriveConfig:
    credentials_json: Path
    folder_id: str
    spreadsheet_prefix: str = "Science Bowl Match"

    @property
    def configured(self) -> bool:
        return bool(self.folder_id) and self.credentials_json.exists()


def load_google_drive_config(config_path: str | Path | None = None) -> GoogleDriveConfig | None:
    raw: dict[str, str] = {}
    if config_path:
        path = Path(config_path)
        if path.exists():
            raw.update(json.loads(path.read_text(encoding="utf-8")))
    else:
        default_path = Path("config/google_drive.json")
        if default_path.exists():
            raw.update(json.loads(default_path.read_text(encoding="utf-8")))

    credentials = raw.get("credentials_json") or os.getenv("BUZZER_GOOGLE_CREDENTIALS")
    folder_id = raw.get("folder_id") or os.getenv("BUZZER_GOOGLE_FOLDER_ID")
    prefix = raw.get("spreadsheet_prefix") or os.getenv("BUZZER_GOOGLE_SHEET_PREFIX") or "Science Bowl Match"

    if not credentials and not folder_id:
        return None
    if not credentials or not folder_id:
        raise RuntimeError(
            "Google sync needs both credentials_json and folder_id. "
            "See docs/GOOGLE_DRIVE_SETUP.md."
        )
    return GoogleDriveConfig(Path(credentials), folder_id, prefix)


class GoogleDriveSheetsSync:
    """Creates a native Google Sheet in a Drive folder and writes match rows."""

    def __init__(self, config: GoogleDriveConfig) -> None:
        if not config.credentials_json.exists():
            raise RuntimeError(f"Google credentials file not found: {config.credentials_json}")
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Install google-api-python-client and google-auth for Google Drive sync"
            ) from exc

        credentials = Credentials.from_service_account_file(
            str(config.credentials_json),
            scopes=SCOPES,
        )
        self.config = config
        self.drive = build("drive", "v3", credentials=credentials)
        self.sheets = build("sheets", "v4", credentials=credentials)

    def create_spreadsheet(self, rows: list[list[object]], round_name: str) -> dict[str, str]:
        timestamp = datetime.now().strftime("%Y-%m-%d %H%M")
        title = f"{self.config.spreadsheet_prefix} - {round_name} - {timestamp}"
        metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "parents": [self.config.folder_id],
        }
        file = (
            self.drive.files()
            .create(body=metadata, fields="id, webViewLink")
            .execute()
        )
        spreadsheet_id = file["id"]
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        return {
            "id": spreadsheet_id,
            "url": file.get("webViewLink", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"),
            "title": title,
        }

