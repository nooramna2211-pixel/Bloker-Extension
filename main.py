"""Visible Windows tray controller for the Bloker browser content filter.

The browser extension performs filtering on its explicitly declared sites. This
desktop app stores the protection state and serves it to the extension through
Chrome/Edge Native Messaging; it does not inspect unrelated windows or keystrokes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

import pystray
from PIL import Image, ImageDraw

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only integration
    winreg = None


APP_NAME = "Bloker Protection"
NATIVE_HOST_NAME = "com.bloker.content_filter"
REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_NATIVE_HOST_KEY = (
    rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}"
)
EDGE_NATIVE_HOST_KEY = (
    rf"Software\Microsoft\Edge\NativeMessagingHosts\{NATIVE_HOST_NAME}"
)
PBKDF2_ITERATIONS = 310_000
EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "BlokerProtection" / "settings.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"enabled": True}
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read settings file {path}: {exc}") from exc

    if not isinstance(settings, dict) or not isinstance(settings.get("enabled"), bool):
        raise RuntimeError(f"Settings file {path} has an invalid format.")
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


def password_record(password: str, salt: bytes | None = None) -> dict[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }


def verify_password(password: str, record: dict[str, str]) -> bool:
    try:
        salt = base64.b64decode(record["salt"], validate=True)
        expected = base64.b64decode(record["hash"], validate=True)
    except (KeyError, TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(actual, expected)


def make_tray_image() -> Image.Image:
    image = Image.new("RGB", (64, 64), "#177245")
    draw = ImageDraw.Draw(image)
    draw.ellipse((14, 14, 50, 50), fill="white")
    draw.line((23, 33, 30, 40, 43, 24), fill="#177245", width=5)
    return image


class ProtectionApp:
    def __init__(self) -> None:
        if winreg is None:
            raise RuntimeError("Bloker Protection can only run on Windows.")

        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("440x390")
        self.root.minsize(400, 360)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.configure(padx=22, pady=18)

        self.status_label = ttk.Label(self.root, font=("Segoe UI", 18, "bold"))
        self.status_label.pack(pady=(8, 4))
        ttk.Label(
            self.root,
            text="Search filtering runs in the Bloker browser extension.",
            wraplength=380,
            justify="center",
        ).pack(pady=(0, 14))

        self.toggle_button = ttk.Button(
            self.root, command=self.toggle_protection, width=28
        )
        self.toggle_button.pack(pady=5)
        ttk.Button(
            self.root, text="Change administrator password", command=self.change_password
        ).pack(pady=8)

        ttk.Separator(self.root).pack(fill="x", pady=12)
        ttk.Label(
            self.root,
            text="Extension connection",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            self.root,
            text="Load the extension first, then enter its ID(s) from "
            "chrome://extensions. Separate Chrome and Edge IDs with commas.",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(3, 5))
        self.extension_id = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.extension_id).pack(fill="x")
        ttk.Button(
            self.root,
            text="Install / update browser connection",
            command=self.install_native_host,
        ).pack(pady=8)
        ttk.Button(
            self.root,
            text="Enable Windows startup",
            command=self.register_startup,
        ).pack(pady=2)
        ttk.Label(
            self.root,
            text="Closing this window hides it to the system tray. Protection-state "
            "changes apply to pages when they next load or reload.",
            wraplength=380,
            justify="center",
            foreground="#555555",
        ).pack(side="bottom", pady=(12, 0))

        self._refresh_status()
        self.tray_icon = pystray.Icon(
            "bloker_protection",
            make_tray_image(),
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("Open", self._show_from_tray, default=True),
                pystray.MenuItem("Exit", self._exit_from_tray),
            ),
        )
        self.tray_thread = threading.Thread(
            target=self.tray_icon.run, name="bloker-system-tray", daemon=True
        )
        self.tray_thread.start()

        if "--startup" in sys.argv:
            self.root.withdraw()

        if not self.settings.get("password"):
            self.root.after(150, self._set_initial_password)

    def _refresh_status(self) -> None:
        enabled = self.settings["enabled"]
        self.status_label.configure(
            text="Protection ON" if enabled else "Protection OFF",
            foreground="#16803c" if enabled else "#c62828",
        )
        self.toggle_button.configure(
            text="Turn protection OFF" if enabled else "Turn protection ON"
        )

    def _persist(self) -> bool:
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showerror(
                APP_NAME, f"Could not save protection settings: {exc}", parent=self.root
            )
            return False
        return True

    def _set_initial_password(self) -> None:
        while not self.settings.get("password"):
            first = simpledialog.askstring(
                APP_NAME,
                "Create an administrator password:",
                show="*",
                parent=self.root,
            )
            if first is None:
                messagebox.showwarning(
                    APP_NAME,
                    "A password is required before protection can be controlled.",
                    parent=self.root,
                )
                continue
            if len(first) < 8:
                messagebox.showerror(
                    APP_NAME,
                    "Use a password with at least 8 characters.",
                    parent=self.root,
                )
                continue
            confirmation = simpledialog.askstring(
                APP_NAME, "Confirm the password:", show="*", parent=self.root
            )
            if first != confirmation:
                messagebox.showerror(
                    APP_NAME, "The passwords did not match.", parent=self.root
                )
                continue
            self.settings["password"] = password_record(first)
            if not self._persist():
                del self.settings["password"]

    def toggle_protection(self) -> None:
        if self.settings["enabled"]:
            password = simpledialog.askstring(
                APP_NAME,
                "Enter the administrator password to turn protection off:",
                show="*",
                parent=self.root,
            )
            record = self.settings.get("password")
            if not password or not isinstance(record, dict) or not verify_password(
                password, record
            ):
                messagebox.showerror(
                    APP_NAME, "Incorrect password; protection remains on.", parent=self.root
                )
                return
            self.settings["enabled"] = False
        else:
            self.settings["enabled"] = True
        if not self._persist():
            self.settings["enabled"] = not self.settings["enabled"]
            return
        self._refresh_status()

    def change_password(self) -> None:
        current = simpledialog.askstring(
            APP_NAME, "Current password:", show="*", parent=self.root
        )
        record = self.settings.get("password")
        if not current or not isinstance(record, dict) or not verify_password(
            current, record
        ):
            messagebox.showerror(APP_NAME, "Incorrect password.", parent=self.root)
            return
        new_password = simpledialog.askstring(
            APP_NAME,
            "New password (at least 8 characters):",
            show="*",
            parent=self.root,
        )
        if not new_password or len(new_password) < 8:
            messagebox.showerror(
                APP_NAME, "Use a password with at least 8 characters.", parent=self.root
            )
            return
        confirmation = simpledialog.askstring(
            APP_NAME, "Confirm the new password:", show="*", parent=self.root
        )
        if confirmation != new_password:
            messagebox.showerror(
                APP_NAME, "The passwords did not match.", parent=self.root
            )
            return
        previous_record = self.settings["password"]
        self.settings["password"] = password_record(new_password)
        if not self._persist():
            self.settings["password"] = previous_record
            return
        messagebox.showinfo(APP_NAME, "Password updated.", parent=self.root)

    def install_native_host(self) -> None:
        extension_ids = [
            item.strip() for item in self.extension_id.get().split(",") if item.strip()
        ]
        if not extension_ids:
            messagebox.showerror(
                APP_NAME,
                "Please enter a valid extension ID.",
                parent=self.root,
            )
            return
            
            return

        host_executable = Path(__file__).resolve().parent / "dist" / "bloker-native-host.exe"
        if not host_executable.is_file():
            messagebox.showerror(
                APP_NAME,
                "The native host executable was not found. Build it first with "
                "`pyinstaller --onefile --name bloker-native-host native_host.py`.",
                parent=self.root,
            )
            return

        host_manifest = {
            "name": NATIVE_HOST_NAME,
            "description": "Bloker browser protection state provider",
            "path": str(host_executable),
            "type": "stdio",
            "allowed_origins": [
                f"chrome-extension://{extension_id}/" for extension_id in extension_ids
            ],
        }
        manifest_path = settings_path().with_name("native-host-manifest.json")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(host_manifest, indent=2) + "\n", encoding="utf-8"
        )

        try:
            for key_path in (REGISTRY_NATIVE_HOST_KEY, EDGE_NATIVE_HOST_KEY):
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.SetValueEx(
                        key, "", 0, winreg.REG_SZ, str(manifest_path.resolve())
                    )
        except OSError as exc:
            messagebox.showerror(
                APP_NAME, f"Could not register the browser connection: {exc}", parent=self.root
            )
            return

        messagebox.showinfo(
            APP_NAME,
            "Browser connection installed for Chrome and Edge. Reload the extension "
            "and its open tabs to apply the current protection state.",
            parent=self.root,
        )

    def register_startup(self) -> None:
        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        command_line = f'"{executable}" "{Path(__file__).resolve()}" --startup'
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command_line)
        except OSError as exc:
            messagebox.showerror(
                APP_NAME, f"Could not enable Windows startup: {exc}", parent=self.root
            )
            return
        messagebox.showinfo(
            APP_NAME,
            "Bloker will start when you sign in to this Windows account. "
            "Remove its entry from Windows Startup Apps to disable this.",
            parent=self.root,
        )

    def hide_to_tray(self) -> None:
        self.root.withdraw()

    def _show_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def _exit_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.root.after(0, self._exit)

    def _exit(self) -> None:
        self.tray_icon.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    try:
        ProtectionApp().run()
    except (OSError, RuntimeError) as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, str(exc), parent=root)
        root.destroy()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())