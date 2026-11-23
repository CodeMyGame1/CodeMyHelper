"""
Centralized PocketBase Database Layer for Shisho.
Provides connection pooling/singleton with admin authentication,
user identity mapping, multipart file upload helpers, and async wrappers.
"""

import asyncio
import functools
import json
import os
from typing import Any, Callable, TypeVar, Union

from pocketbase import PocketBase
from pocketbase.client import FileUpload

T = TypeVar("T")

_pb_client: PocketBase | None = None


def get_pb_url(url: str | None = None) -> str:
    """
    Normalize and return the PocketBase base URL.
    Prepends 'https://' if scheme is missing.
    """
    base_url = url if url is not None else os.getenv("POCKETBASE_URL", "")
    if not base_url:
        return ""
    if "://" not in base_url:
        return f"https://{base_url}"
    return base_url


def get_pb_client(
    url: str | None = None,
    user: str | None = None,
    password: str | None = None,
    refresh: bool = False,
) -> PocketBase:
    """
    Get or create an authenticated PocketBase client instance.
    Uses admin credentials from environment variables if not provided.
    Reuses existing valid authentication token if available unless refresh=True.
    """
    global _pb_client

    target_url = get_pb_url(url)
    target_user = user if user is not None else os.getenv("POCKETBASE_USER", "")
    target_password = (
        password if password is not None else os.getenv("POCKETBASE_PASSWORD", "")
    )

    if not target_url or not target_user or not target_password:
        raise ValueError("PocketBase configuration missing in environment variables.")

    if not refresh and _pb_client is not None:
        if getattr(_pb_client.auth_store, "is_valid", False):
            return _pb_client

    client = PocketBase(target_url)
    client.collection("users").auth_with_password(target_user, target_password)
    _pb_client = client
    return _pb_client


def validate_pb_token(token: str, url: str | None = None) -> Any:
    """
    Validate a user Bearer token using auth_refresh on shisho_users.
    Uses an isolated client instance to avoid mutating the admin auth state.
    Returns the user record dict/object on success, or None on failure.
    """
    if not token:
        return None
    try:
        target_url = get_pb_url(url)
        client = PocketBase(target_url)
        client.auth_store.save(token, None)
        result = client.collection("shisho_users").auth_refresh()
        return getattr(result, "record", result)
    except Exception:
        return None


def get_discord_user_id(
    pb: Union[PocketBase, Any, str, int, None] = None,
    discord_id: Union[str, int, None] = None,
) -> str | None:
    """
    Look up the PocketBase user ID in `shisho_users` corresponding to the given Discord ID.
    Returns the PocketBase user record ID string if found, otherwise None.

    Supports both get_discord_user_id(pb, discord_id) and get_discord_user_id(discord_id).
    """
    # Allow (discord_id) positional call
    if isinstance(pb, (str, int)) and discord_id is None:
        discord_id = pb
        client = None
    else:
        client = pb

    if not discord_id:
        return None

    clean_did = "".join(c for c in str(discord_id) if c.isdigit())
    if not clean_did:
        return None

    try:
        if client is None:
            client = get_pb_client()
        records = client.collection("shisho_users").get_full_list(
            query_params={"filter": f"discord_id='{clean_did}'"}
        )
        if records:
            return records[0].id
        return None
    except Exception:
        return None


def get_pb_user_discord_id(
    pb: Union[PocketBase, Any, str, None] = None,
    pb_user_id: str | None = None,
) -> str | None:
    """
    Reverse lookup: Get the Discord ID string from a PocketBase `shisho_users` record ID.

    Supports both get_pb_user_discord_id(pb, pb_user_id) and get_pb_user_discord_id(pb_user_id).
    """
    # Allow (pb_user_id) positional call
    if isinstance(pb, str) and pb_user_id is None and not hasattr(pb, "collection"):
        pb_user_id = pb
        client = None
    else:
        client = pb

    if not pb_user_id:
        return None

    try:
        if client is None:
            client = get_pb_client()
        user_record = client.collection("shisho_users").get_one(pb_user_id)
        return getattr(user_record, "discord_id", None)
    except Exception:
        return None


def get_user_instructions(
    user_id: Union[str, int],
    pb: Any = None,
) -> list[dict]:
    """
    Retrieve stored persistent bot instructions/rules for a user from PocketBase.
    Returns a list of dicts, e.g.:
    [{"id": 1, "rule": "Reply in lowercase"}, {"id": 2, "rule": "Address me as boss"}]
    Returns [] if the user is unregistered, has no instructions, or on error.
    """
    if not user_id:
        return []

    clean_did = "".join(c for c in str(user_id) if c.isdigit())
    if not clean_did:
        return []

    try:
        client = pb if pb is not None else get_pb_client()
        pb_user_id = get_discord_user_id(client, clean_did)
        if not pb_user_id:
            return []

        user_record = client.collection("shisho_users").get_one(pb_user_id)
        raw = getattr(user_record, "bot_instructions", None)
        if raw is None and isinstance(user_record, dict):
            raw = user_record.get("bot_instructions")

        if not raw:
            return []

        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except Exception:
                return []
        elif isinstance(raw, list):
            parsed = raw
        else:
            return []

        if isinstance(parsed, list):
            valid_rules = []
            for item in parsed:
                if isinstance(item, dict) and "rule" in item:
                    valid_rules.append(
                        {
                            "id": item.get("id", len(valid_rules) + 1),
                            "rule": str(item["rule"]),
                        }
                    )
            return valid_rules
        return []
    except Exception:
        return []


def update_user_instructions(
    user_id: Union[str, int],
    instructions: list[dict],
    pb: Any = None,
) -> bool:
    """
    Update stored persistent bot instructions for a user in PocketBase.
    Accepts a list of rule dicts (e.g. [{"id": 1, "rule": "..."}]).
    Saves to the 'bot_instructions' field in PocketBase.
    Returns True if successfully updated, False otherwise.
    """
    if not user_id:
        return False

    clean_did = "".join(c for c in str(user_id) if c.isdigit())
    if not clean_did:
        return False

    try:
        client = pb if pb is not None else get_pb_client()
        pb_user_id = get_discord_user_id(client, clean_did)
        if not pb_user_id:
            return False

        clean_instructions = []
        if isinstance(instructions, list):
            for idx, item in enumerate(instructions, start=1):
                if isinstance(item, dict) and "rule" in item:
                    clean_instructions.append(
                        {
                            "id": item.get("id", idx),
                            "rule": str(item["rule"]),
                        }
                    )

        try:
            client.collection("shisho_users").update(
                pb_user_id, {"bot_instructions": clean_instructions}
            )
            return True
        except Exception:
            client.collection("shisho_users").update(
                pb_user_id, {"bot_instructions": json.dumps(clean_instructions)}
            )
            return True
    except Exception:
        return False


def clear_user_instructions(
    user_id: Union[str, int],
    pb: Any = None,
) -> bool:
    """
    Clears all custom bot instructions for a user in PocketBase (resets to []).
    Returns True on success, False otherwise.
    """
    return update_user_instructions(user_id, [], pb=pb)


class MultiFileUpload(FileUpload):
    """FileUpload wrapper supporting a list of (filename, bytes) for repeated form fields."""

    def __init__(self, file_data_list: list[tuple[str, bytes]]):
        self.file_data_list = file_data_list

    def get(self, key: str):
        return tuple((key, data) for data in self.file_data_list)


class BodyDict(dict):
    """Dictionary wrapper that yields regular fields and FileUpload instances on .items()."""

    def __init__(self, regular_data: dict[str, Any], file_uploads: dict[str, Any]):
        super().__init__(regular_data)
        self.regular_data = regular_data
        self.file_uploads = file_uploads

    def items(self):
        for k, v in self.regular_data.items():
            yield k, v
        for k, v in self.file_uploads.items():
            yield k, v


def prepare_file_upload_payload(
    data: dict[str, Any],
    files: dict[str, tuple[str, bytes] | list[tuple[str, bytes]] | FileUpload]
    | None = None,
) -> dict[str, Any]:
    """
    Combines regular dictionary data with file attachments for PocketBase create/update.
    """
    if not files:
        return data

    file_uploads: dict[str, Any] = {}
    for field_name, file_item in files.items():
        if not file_item:
            continue
        if isinstance(file_item, FileUpload):
            file_uploads[field_name] = file_item
        elif isinstance(file_item, list):
            file_uploads[field_name] = MultiFileUpload(file_item)
        elif isinstance(file_item, tuple):
            file_uploads[field_name] = FileUpload(file_item)
        else:
            raise ValueError(
                f"Unsupported file upload format for field '{field_name}': {type(file_item)}"
            )

    if not file_uploads:
        return data

    return BodyDict(data, file_uploads)


async def run_in_executor(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Run a blocking/synchronous callable in a background thread.
    """
    if kwargs:
        return await asyncio.to_thread(functools.partial(func, *args, **kwargs))
    return await asyncio.to_thread(func, *args)


def _get_pb_field(obj: Any, attr: str, fallback: Any = "") -> Any:
    """Safely read a field from either a PocketBase Record or dict."""
    val = getattr(obj, attr, None)
    if val is None and isinstance(obj, dict):
        val = obj.get(attr)
    elif val is None and hasattr(obj, "get"):
        val = obj.get(attr)
    return val if val is not None else fallback


def resolve_user_book_id(
    pb: Any, pb_user_id: str, book_query: str | None
) -> tuple[str, str]:
    """
    Resolve a book ID, title, author, or ISBN to a (record_id, title) tuple
    owned by `pb_user_id` in `shisho_books`.
    Returns ("", "") when cleared/empty or no matching book is found.
    """
    if not book_query or not str(book_query).strip() or not pb_user_id:
        return ("", "")

    clean_q = str(book_query).strip()
    if clean_q.lower() in ("none", "clear", "unlink", "null"):
        return ("", "")

    # 1. Exact ID lookup
    try:
        rec = pb.collection("shisho_books").get_one(clean_q)
        if rec and _get_pb_field(rec, "owner") == pb_user_id:
            return (
                str(_get_pb_field(rec, "id")),
                str(_get_pb_field(rec, "title") or "Untitled"),
            )
    except Exception:
        pass

    # 2. Search by title, ISBN, or author
    try:
        clean_isbn = clean_q.replace("-", "").replace(" ", "").strip()
        safe_q = clean_q.replace("'", "\\'")
        safe_isbn = (clean_isbn or clean_q).replace("'", "\\'")
        filter_str = (
            f"owner = '{pb_user_id}' && "
            f"(title ~ '{safe_q}' || isbn ~ '{safe_isbn}' || author ~ '{safe_q}')"
        )
        records = pb.collection("shisho_books").get_full_list(
            query_params={"filter": filter_str}
        )
        if not records:
            return ("", "")

        matched = None
        for r in records:
            r_title = str(_get_pb_field(r, "title")).strip().lower()
            r_isbn = str(_get_pb_field(r, "isbn")).replace("-", "").replace(" ", "").strip()
            if r_title == clean_q.lower() or (clean_isbn and r_isbn == clean_isbn):
                matched = r
                break
        if not matched:
            matched = records[0]

        return (
            str(_get_pb_field(matched, "id")),
            str(_get_pb_field(matched, "title") or "Untitled"),
        )
    except Exception:
        return ("", "")


def get_user_book_titles_map(pb: Any, pb_user_id: str) -> dict[str, str]:
    """
    Fetch all `shisho_books` owned by `pb_user_id` and return a {record_id: title} map.
    """
    if not pb_user_id:
        return {}
    try:
        records = pb.collection("shisho_books").get_full_list(
            query_params={"filter": f"owner = '{pb_user_id}'"}
        )
        result: dict[str, str] = {}
        for r in records:
            rec_id = _get_pb_field(r, "id")
            if rec_id:
                result[str(rec_id)] = str(_get_pb_field(r, "title") or "Untitled")
        return result
    except Exception:
        return {}


def user_book_autocomplete_choices(
    discord_user_id: str,
    current: str,
    include_unlink: bool = False,
) -> list[tuple[str, str]]:
    """
    Synchronous helper returning up to 25 (display_label, book_id) tuples
    for Discord slash command book autocompletes.
    """
    try:
        pb = get_pb_client()
        pb_user_id = get_discord_user_id(pb, discord_user_id)
        if not pb_user_id:
            return []

        records = pb.collection("shisho_books").get_full_list(
            query_params={"filter": f"owner = '{pb_user_id}'", "sort": "-id"}
        )
        clean_cur = (current or "").strip().lower()
        choices: list[tuple[str, str]] = []

        if include_unlink and (
            not clean_cur or any(k.startswith(clean_cur) for k in ("none", "unlink", "clear"))
        ):
            choices.append(("[None / Unlink Book]", "none"))

        for r in records:
            rec_id = str(_get_pb_field(r, "id"))
            title = str(_get_pb_field(r, "title") or "Untitled")
            author = str(_get_pb_field(r, "author"))
            isbn = str(_get_pb_field(r, "isbn"))
            display = f"{title} by {author}" if author else title
            if (
                clean_cur
                and clean_cur not in display.lower()
                and clean_cur not in isbn.lower()
            ):
                continue
            choices.append((display[:100], rec_id or title))

        return choices[:25]
    except Exception:
        return []
