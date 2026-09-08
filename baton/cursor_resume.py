"""Patch txcript-imported Cursor sessions so `agent --resume` can start.

txcript writes ConversationStateStructure field 26 (`conversation_started_timestamp_ms`)
and omits field 27 (`conversation_started_time_zone`). Cursor's API then rejects the
resume with: conversationStartedTimestampMs was set without conversationStartedTimeZone.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from baton.dirs import cursor_workspace_chats_dir

# agent.v1.ConversationStateStructure
_FIELD_STARTED_MS = 26
_FIELD_STARTED_TZ = 27


def iana_timezone() -> str:
    """Best-effort IANA zone for Cursor (e.g. America/New_York, not EDT)."""
    env = (os.environ.get("TZ") or "").strip()
    if env and env not in {":localtime", "localtime"}:
        return env.lstrip(":")
    localtime = Path("/etc/localtime")
    try:
        target = str(localtime.resolve())
    except OSError:
        return "UTC"
    return iana_timezone_from_path(target)


def iana_timezone_from_path(target: str) -> str:
    """Parse an IANA name out of a zoneinfo symlink target."""
    marker = "/zoneinfo/"
    if marker in target:
        zone = target.rsplit(marker, 1)[-1]
        if zone:
            return zone
    return "UTC"


def seal_imported_cursor_session(session_id: str, cwd: str | Path) -> bool:
    """Append timezone to the root proto if txcript left it missing. Return True if patched."""
    sid = (session_id or "").strip()
    if not sid:
        return False
    db_path = cursor_workspace_chats_dir(cwd) / sid / "store.db"
    if not db_path.is_file():
        return False
    zone = iana_timezone()
    return _patch_store(db_path, zone)


def _patch_store(db_path: Path, zone: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = '0'").fetchone()
        if not row:
            return False
        meta = _decode_meta(row[0])
        root_id = str(meta.get("latestRootBlobId") or "")
        if not root_id:
            return False
        blob = conn.execute("SELECT data FROM blobs WHERE id = ?", (root_id,)).fetchone()
        if not blob or blob[0] is None:
            return False
        data = bytes(blob[0])
        patched = _ensure_timezone(data, zone)
        if patched is None:
            return False
        new_id = hashlib.sha256(patched).hexdigest()
        if new_id == root_id:
            return False
        conn.execute("INSERT OR REPLACE INTO blobs (id, data) VALUES (?, ?)", (new_id, patched))
        meta["latestRootBlobId"] = new_id
        encoded = _encode_meta(meta, original=row[0])
        conn.execute("UPDATE meta SET value = ? WHERE key = '0'", (encoded,))
        conn.commit()
    finally:
        conn.close()
    return True


def _decode_meta(value: str) -> dict:
    text = value
    if all(c in "0123456789abcdefABCDEF" for c in value[:16]) and len(value) % 2 == 0:
        try:
            text = bytes.fromhex(value).decode("utf-8")
        except ValueError:
            text = value
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("cursor meta is not an object")
    return obj


def _encode_meta(meta: dict, *, original: str) -> str:
    payload = json.dumps(meta, separators=(",", ":"))
    if all(c in "0123456789abcdefABCDEF" for c in original[:16]):
        return payload.encode("utf-8").hex()
    return payload


def _ensure_timezone(data: bytes, zone: str) -> bytes | None:
    fields = _top_level_fields(data)
    if _FIELD_STARTED_TZ in fields:
        return None
    if _FIELD_STARTED_MS not in fields:
        return None
    return data + _len_field(_FIELD_STARTED_TZ, zone.encode("utf-8"))


def _top_level_fields(buf: bytes) -> set[int]:
    seen: set[int] = set()
    i = 0
    n = len(buf)
    while i < n:
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        seen.add(field)
        if wire == 0:
            _, i = _varint(buf, i)
        elif wire == 1:
            i += 8
        elif wire == 2:
            length, i = _varint(buf, i)
            i += length
        elif wire == 5:
            i += 4
        else:
            break
        if i > n:
            break
    return seen


def _len_field(field: int, payload: bytes) -> bytes:
    out = bytearray()
    _put_varint(out, (field << 3) | 2)
    _put_varint(out, len(payload))
    out.extend(payload)
    return bytes(out)


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    n = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if b < 0x80:
            return n, i
        shift += 7
        if shift > 63:
            break
    raise ValueError("truncated protobuf varint")


def _put_varint(out: bytearray, value: int) -> None:
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
