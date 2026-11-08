"""Executable Native Messaging bridge used by the browser extension."""

import json
import os
import struct
import sys
from pathlib import Path


MAX_MESSAGE_BYTES = 1024 * 1024


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "BlokerProtection" / "settings.json"


def read_exact(length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sys.stdin.buffer.read(length - len(chunks))
        if not chunk:
            raise ValueError("Unexpected end of native messaging input.")
        chunks.extend(chunk)
    return bytes(chunks)


def read_request() -> dict:
    header = sys.stdin.buffer.read(4)
    if not header:
        raise EOFError
    if len(header) != 4:
        header += read_exact(4 - len(header))
    length = struct.unpack("<I", header)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError("Native messaging request exceeded the size limit.")
    request = json.loads(read_exact(length).decode("utf-8"))
    if not isinstance(request, dict):
        raise ValueError("Native messaging request must be a JSON object.")
    return request


def send_response(response: dict) -> None:
    payload = json.dumps(response, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(payload)))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        request = read_request()
        if request.get("type") != "get-state":
            raise ValueError("Unsupported native messaging request.")
        settings = json.loads(settings_path().read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            raise ValueError("Protection settings have an invalid format.")
        enabled = settings.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("Protection state is missing or invalid.")
        send_response({"enabled": enabled})
    except EOFError:
        return 0
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        log_path = settings_path().with_name("native-host.log")
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{exc}\n")
        except OSError:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
