#!/usr/bin/env python3
"""Download a team's data submission folder from the shared OpenH-RF Google Drive.

Prompts for a team name (a subfolder of the shared Drive folder) and downloads
it into ``submissions/<team name>/``, preserving the folder structure.

Setup (one-time):
  1. In Google Cloud Console, enable the "Google Drive API" for a project.
  2. Create an OAuth client ID of type "Desktop app" and download the JSON.
  3. Save it as scripts/credentials.json (gitignored).
  4. pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
     (or: uv sync --extra gdrive)

The first run opens a browser to sign in with a Google account that has
access to the shared folder; the resulting token is cached in
scripts/.gdrive_token.json so future runs don't need to re-authenticate.

Usage:
  python scripts/download_submission.py
  python scripts/download_submission.py --team USTB
  python scripts/download_submission.py --team USTB --overwrite
  python scripts/download_submission.py --team USTB --sample
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
except ImportError:
    print(
        "Missing Google API packages. Install them with:\n"
        "  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2\n"
        "or:\n"
        "  uv sync --extra gdrive",
        file=sys.stderr,
    )
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# https://drive.google.com/drive/u/0/folders/1OgTKqsr5AzHHA-D769E5j-z0KevrwEy1
ROOT_FOLDER_ID = "1OgTKqsr5AzHHA-D769E5j-z0KevrwEy1"

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_CREDENTIALS_PATH = SCRIPT_DIR / "credentials.json"
DEFAULT_TOKEN_PATH = SCRIPT_DIR / ".gdrive_token.json"

FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_APPS_PREFIX = "application/vnd.google-apps."
HDF5_SUFFIXES = {".hdf5", ".h5"}

# Google-native files must be exported rather than downloaded directly.
EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": (
        "application/pdf",
        ".pdf",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/pdf",
        ".pdf",
    ),
}


def get_drive_service(credentials_path: Path, token_path: Path):
    if not credentials_path.exists():
        print(
            f"No OAuth client secrets found at {credentials_path}.\n"
            "Create one at https://console.cloud.google.com/apis/credentials "
            "(OAuth client ID -> Desktop app) and save the downloaded JSON there.",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_children(service, folder_id: str) -> list[dict]:
    """List all non-trashed children of a Drive folder (handles pagination)."""
    items = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageSize=1000,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        items.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items


def list_subfolders(service, folder_id: str) -> dict[str, str]:
    return {
        item["name"]: item["id"]
        for item in list_children(service, folder_id)
        if item["mimeType"] == FOLDER_MIME
    }


def choose_team(service, requested: str | None) -> tuple[str, str]:
    subfolders = list_subfolders(service, ROOT_FOLDER_ID)
    if not subfolders:
        print("No subfolders found in the shared Drive folder.", file=sys.stderr)
        sys.exit(1)

    if requested:
        # Case-insensitive exact match.
        for name, folder_id in subfolders.items():
            if name.lower() == requested.lower():
                return name, folder_id
        print(f"No submission folder named '{requested}' found.", file=sys.stderr)
        print("Available submissions:", file=sys.stderr)
        for name in sorted(subfolders):
            print(f"  - {name}", file=sys.stderr)
        sys.exit(1)

    print("Available data submissions:")
    for name in sorted(subfolders):
        print(f"  - {name}")
    choice = input("Which submission do you want to download? ").strip()
    for name, folder_id in subfolders.items():
        if name.lower() == choice.lower():
            return name, folder_id
    print(f"No submission folder named '{choice}' found.", file=sys.stderr)
    sys.exit(1)


def download_file(service, file_id: str, mime_type: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if mime_type.startswith(GOOGLE_APPS_PREFIX):
        export_mime, suffix = EXPORT_MIME_MAP.get(mime_type, (None, None))
        if not export_mime:
            print(f"  skipping unsupported Google file type ({mime_type}): {dest_path.name}")
            return
        dest_path = dest_path.with_suffix(suffix)
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

    buffer = io.FileIO(dest_path, "wb")
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.close()


def download_folder(
    service,
    folder_id: str,
    dest_dir: Path,
    sample: bool,
    sample_state: dict,
    rel_path: str = "",
) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)

    for item in list_children(service, folder_id):
        name = item["name"]
        item_rel_path = f"{rel_path}/{name}" if rel_path else name

        if item["mimeType"] == FOLDER_MIME:
            download_folder(
                service, item["id"], dest_dir / name, sample, sample_state, item_rel_path
            )
            continue

        is_hdf5 = Path(name).suffix.lower() in HDF5_SUFFIXES
        if sample and is_hdf5:
            if sample_state["hdf5_downloaded"]:
                print(f"  skipping (sample mode): {item_rel_path}")
                continue
            sample_state["hdf5_downloaded"] = True

        print(f"  downloading: {item_rel_path}")
        download_file(service, item["id"], item["mimeType"], dest_dir / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", help="Team/submission folder name (skips the interactive prompt).")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow downloading into an already-existing submissions/<team> directory.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Only download one .hdf5/.h5 file (folder structure is still preserved).",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help=f"Path to OAuth client secrets JSON (default: {DEFAULT_CREDENTIALS_PATH}).",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help=f"Path to cache the OAuth token (default: {DEFAULT_TOKEN_PATH}).",
    )
    args = parser.parse_args()

    # Fail fast (before triggering an OAuth prompt) if we already know the destination.
    if args.team and not args.overwrite:
        early_dest = REPO_ROOT / "submissions" / args.team
        if early_dest.exists():
            print(
                f"{early_dest} already exists. Re-run with --overwrite to download into it anyway.",
                file=sys.stderr,
            )
            sys.exit(1)

    service = get_drive_service(args.credentials, args.token)
    team_name, folder_id = choose_team(service, args.team)

    dest_dir = REPO_ROOT / "submissions" / team_name
    if dest_dir.exists() and not args.overwrite:
        print(
            f"{dest_dir} already exists. Re-run with --overwrite to download into it anyway.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Downloading '{team_name}' into {dest_dir}" + (" (sample mode)" if args.sample else ""))
    download_folder(service, folder_id, dest_dir, args.sample, {"hdf5_downloaded": False})
    print("Done.")


if __name__ == "__main__":
    main()
