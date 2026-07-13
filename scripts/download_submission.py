#!/usr/bin/env python3
"""Download a team's data submission folder from the shared OpenH-RF Google Drive.

Prompts for a team name (a subfolder of the shared Drive folder) and downloads
it into ``submissions/<team name>/``, preserving the folder structure.

Re-running is safe: existing local files are left alone unless the remote
file's size has changed, and nothing already on disk is ever deleted, so it's
cheap to re-run after a new file shows up in a team's Drive folder.

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
  python scripts/download_submission.py --team TEAM
  python scripts/download_submission.py --team TEAM --overwrite
  python scripts/download_submission.py --team TEAM --sample
  python scripts/download_submission.py --team TEAM --subfolder SUBFOLDER
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


def _list_by_query(service, q: str) -> list[dict]:
    items = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=q,
                fields=(
                    "nextPageToken, files(id, name, mimeType, size, trashed, "
                    "parents, owners(emailAddress))"
                ),
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


def _list_collaborator_emails(service, folder_id: str) -> list[str]:
    perms = (
        service.permissions()
        .list(fileId=folder_id, fields="permissions(type, emailAddress)", supportsAllDrives=True)
        .execute()
    )
    return [
        p["emailAddress"]
        for p in perms.get("permissions", [])
        if p.get("type") == "user" and p.get("emailAddress")
    ]


def list_children(service, folder_id: str, include_trashed: bool = False) -> list[dict]:
    """List children of a Drive folder (handles pagination).

    Caveat: a non-owner "removing" a shared item only trashes it for their
    own account - the item stays fully intact for everyone else. But Drive's
    search index excludes such an item from *any query's results*, even
    though it still resolves fine as a query *anchor* (``files.get`` by ID,
    or "'<its id>' in parents" to list its own children, both work). That
    means a folder trashed-for-this-account is invisible as an entry in its
    parent's listing, even though its own children remain fully listable
    once you know its ID.

    ``include_trashed`` recovers such folders (one level at a time) by
    scanning what the folder's collaborators own and checking, for anything
    not directly visible here, whether *its* parent is this folder - i.e.
    resolving one hop up via a direct ID lookup (unaffected by the search
    exclusion). The recovered folder is surfaced as a normal child entry, so
    the caller's own recursion finds everything beneath it the usual way.
    """
    trashed_clause = "" if include_trashed else " and trashed = false"
    items = _list_by_query(service, f"'{folder_id}' in parents{trashed_clause}")

    if include_trashed:
        seen_ids = {item["id"] for item in items}
        hidden_parent_cache: dict[str, dict | None] = {}
        for email in _list_collaborator_emails(service, folder_id):
            for candidate in _list_by_query(service, f"'{email}' in owners"):
                if candidate["id"] in seen_ids or candidate["mimeType"] == FOLDER_MIME:
                    continue
                parent_id = (candidate.get("parents") or [None])[0]
                if not parent_id or parent_id == folder_id:
                    continue  # already covered by the direct containment query above
                if parent_id not in hidden_parent_cache:
                    try:
                        parent_meta = (
                            service.files()
                            .get(
                                fileId=parent_id,
                                fields="id, name, parents",
                                supportsAllDrives=True,
                            )
                            .execute()
                        )
                    except Exception:
                        parent_meta = None
                    hidden_parent_cache[parent_id] = parent_meta
                parent_meta = hidden_parent_cache[parent_id]
                if not parent_meta or folder_id not in (parent_meta.get("parents") or []):
                    continue
                if parent_id not in seen_ids:
                    seen_ids.add(parent_id)
                    items.append(
                        {
                            "id": parent_id,
                            "name": parent_meta["name"],
                            "mimeType": FOLDER_MIME,
                            "trashed": True,
                        }
                    )

    return items


def list_subfolders(service, folder_id: str) -> dict[str, str]:
    return {
        item["name"]: item["id"]
        for item in list_children(service, folder_id)
        if item["mimeType"] == FOLDER_MIME
    }


def resolve_subfolder(service, folder_id: str, subfolder_path: str) -> tuple[str, str]:
    """Walk down ``folder_id`` following a (possibly nested) ``a/b/c`` path.

    Returns the final folder's (name, id).
    """
    name = ""
    for part in subfolder_path.strip("/").split("/"):
        subfolders = list_subfolders(service, folder_id)
        match = next(((n, fid) for n, fid in subfolders.items() if n.lower() == part.lower()), None)
        if match is None:
            print(f"No subfolder named '{part}' found under '{subfolder_path}'.", file=sys.stderr)
            print("Available subfolders at this level:", file=sys.stderr)
            for n in sorted(subfolders):
                print(f"  - {n}", file=sys.stderr)
            sys.exit(1)
        name, folder_id = match
    return name, folder_id


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


def _up_to_date(dest_path: Path, remote_size: str | None) -> bool:
    """Whether a local file already matches the remote file's size.

    Google-native files (docs/sheets/slides) report no ``size``, so they're
    always considered stale and re-downloaded.
    """
    if remote_size is None or not dest_path.exists():
        return False
    try:
        return dest_path.stat().st_size == int(remote_size)
    except (OSError, ValueError):
        return False


def download_folder(
    service,
    folder_id: str,
    dest_dir: Path,
    sample: bool,
    sample_state: dict,
    rel_path: str = "",
    include_trashed: bool = False,
    force: bool = False,
) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)

    for item in list_children(service, folder_id, include_trashed=include_trashed):
        name = item["name"]
        item_rel_path = f"{rel_path}/{name}" if rel_path else name
        if item.get("trashed"):
            item_rel_path += " [trashed]"

        if item["mimeType"] == FOLDER_MIME:
            download_folder(
                service,
                item["id"],
                dest_dir / name,
                sample,
                sample_state,
                item_rel_path,
                include_trashed=include_trashed,
                force=force,
            )
            continue

        is_hdf5 = Path(name).suffix.lower() in HDF5_SUFFIXES
        if sample and is_hdf5:
            if sample_state["hdf5_downloaded"]:
                print(f"  skipping (sample mode): {item_rel_path}")
                continue
            sample_state["hdf5_downloaded"] = True

        dest_path = dest_dir / name
        if not force and _up_to_date(dest_path, item.get("size")):
            print(f"  up to date, skipping: {item_rel_path}")
            continue

        print(f"  downloading: {item_rel_path}")
        download_file(service, item["id"], item["mimeType"], dest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--team", help="Team/submission folder name (skips the interactive prompt)."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Re-download every file even if a local copy of the same size already "
            "exists (by default, unchanged files are left alone)."
        ),
    )
    sample_or_subfolder = parser.add_mutually_exclusive_group()
    sample_or_subfolder.add_argument(
        "--sample",
        action="store_true",
        help="Only download one .hdf5/.h5 file (folder structure is still preserved).",
    )
    sample_or_subfolder.add_argument(
        "--subfolder",
        help=(
            "Only download this subfolder of the team's submission (e.g. "
            "'validation', or a nested path like 'A/B'), saved to "
            "submissions/<team>/<subfolder> instead of the whole submission."
        ),
    )
    parser.add_argument(
        "--include-trashed",
        action="store_true",
        help=(
            "Also download items that show as trashed. A non-owner collaborator "
            "trashing a file only hides it from their own account; it remains "
            "intact and downloadable for everyone else."
        ),
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

    service = get_drive_service(args.credentials, args.token)
    team_name, folder_id = choose_team(service, args.team)

    dest_dir = REPO_ROOT / "submissions" / team_name
    if args.subfolder:
        _, folder_id = resolve_subfolder(service, folder_id, args.subfolder)
        dest_dir = dest_dir / args.subfolder.strip("/")

    print(f"Downloading '{team_name}' into {dest_dir}" + (" (sample mode)" if args.sample else ""))
    download_folder(
        service,
        folder_id,
        dest_dir,
        args.sample,
        {"hdf5_downloaded": False},
        include_trashed=args.include_trashed,
        force=args.overwrite,
    )
    print("Done.")


if __name__ == "__main__":
    main()
