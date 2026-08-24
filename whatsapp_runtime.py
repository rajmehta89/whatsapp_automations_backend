import logging
import os
import threading
import time
from typing import Any

import segno
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv, HistorySyncEv, LoggedOutEv, MessageEv
from neonize.utils import log
from neonize.utils.enum import Presence
from neonize.utils.jid import build_jid

from config import CONV_DB_PATH, NEO_DB_PATH
from database import init_db, save_message
from services import ensure_runtime_directories
from whatsapp import on_history_sync, on_message


class WhatsAppRuntime:
    STARTUP_TIMEOUT_SECONDS = 45

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._client: NewClient | None = None
        self._stop_requested = False
        self._status: dict[str, Any] = {
            "state": "stopped",
            "connected": False,
            "qr_available": False,
            "qr_path": None,
            "last_error": None,
            "last_event_at": None,
            "started_at": None,
            "phone_hint": None,
        }

    def _set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)
            self._status["last_event_at"] = int(time.time())

    def _clear_local_session_files(self) -> None:
        if os.path.exists(NEO_DB_PATH):
            os.remove(NEO_DB_PATH)
        qr_path = os.path.abspath("static/generated/whatsapp-qr.svg")
        if os.path.exists(qr_path):
            os.remove(qr_path)

    def _refresh_client_state(self) -> None:
        client = self._client
        if not client:
            return

        try:
            is_logged_in = bool(client.is_logged_in())
        except Exception:
            is_logged_in = False

        try:
            is_connected = bool(client.is_connected())
        except Exception:
            is_connected = False

        if is_logged_in or is_connected:
            self._set_status(
                state="connected",
                connected=True,
                qr_available=False,
                qr_path=None,
                last_error=None,
            )
            return

        with self._lock:
            started_at = self._status.get("started_at")
            current_state = self._status.get("state")
            qr_available = self._status.get("qr_available")
            last_error = self._status.get("last_error")

        if (
            current_state == "starting"
            and started_at
            and not qr_available
            and not last_error
            and int(time.time()) - int(started_at) > self.STARTUP_TIMEOUT_SECONDS
        ):
            self._set_status(
                state="error",
                connected=False,
                last_error=(
                    "WhatsApp runtime started but no QR was generated within "
                    f"{self.STARTUP_TIMEOUT_SECONDS} seconds. Reset the session and try again."
                ),
            )

    def get_status(self) -> dict[str, Any]:
        self._refresh_client_state()
        with self._lock:
            return dict(self._status)

    def start(self) -> dict[str, Any]:
        with self._lock:
            thread_is_alive = bool(self._thread and self._thread.is_alive())
            current_state = self._status.get("state")
            client = self._client
            started_at = self._status.get("started_at")

        startup_expired = bool(
            current_state == "starting"
            and started_at
            and int(time.time()) - int(started_at) > self.STARTUP_TIMEOUT_SECONDS
        )

        if thread_is_alive and current_state not in {"logged_out", "error", "disconnected"} and not startup_expired:
            return self.get_status()

        if current_state in {"logged_out", "error"} or startup_expired:
            self._stop_requested = True
            if client:
                try:
                    client.disconnect()
                except Exception as exc:
                    logging.exception(exc)
            time.sleep(1)
            try:
                self._clear_local_session_files()
            except Exception as exc:
                logging.exception(exc)
                self._set_status(state="error", connected=False, last_error=str(exc))
                return self.get_status()

        with self._lock:
            self._thread = None
            self._client = None
            self._stop_requested = False
            self._thread = threading.Thread(target=self._run, name="whatsapp-runtime", daemon=True)
            self._thread.start()
            self._status.update(
                {
                    "state": "starting",
                    "connected": False,
                    "qr_available": False,
                    "qr_path": None,
                    "last_error": None,
                    "started_at": int(time.time()),
                }
            )
            return dict(self._status)

    def stop(self) -> dict[str, Any]:
        self._stop_requested = True
        client = self._client
        if client:
            try:
                client.disconnect()
            except Exception as exc:
                logging.exception(exc)
        self._set_status(state="stopped", connected=False)
        return self.get_status()

    def reset_session(self) -> dict[str, Any]:
        self._stop_requested = True
        client = self._client
        if client:
            try:
                if client.is_logged_in():
                    client.logout()
            except Exception as exc:
                logging.exception(exc)
            try:
                client.disconnect()
            except Exception as exc:
                logging.exception(exc)

        self._set_status(
            state="disconnecting",
            connected=False,
            qr_available=False,
            qr_path=None,
            last_error=None,
        )
        time.sleep(1)
        try:
            self._clear_local_session_files()
        except Exception as exc:
            logging.exception(exc)
            self._set_status(state="error", connected=False, last_error=str(exc))
            return self.get_status()

        self._set_status(
            state="stopped",
            connected=False,
            qr_available=False,
            qr_path=None,
            last_error=None,
            phone_hint=None,
        )
        return self.get_status()

    def send_support_reply(self, user_id: str, text: str, save_to_db: bool = True) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("Reply text is required")
        client = self._client
        if not client or not self.get_status().get("connected"):
            raise RuntimeError("WhatsApp is not connected")

        jid = build_jid(user_id.strip())
        client.send_message(jid, text.strip())
        if save_to_db:
            save_message(user_id.strip(), text.strip(), int(time.time()), True)
        return {"ok": True}

    def _write_qr_svg(self, qr_payload: str) -> str:
        ensure_runtime_directories()
        os.makedirs("static/generated", exist_ok=True)
        qr_path = os.path.abspath("static/generated/whatsapp-qr.svg")
        qr_code = segno.make(qr_payload)
        qr_code.save(qr_path, scale=6, border=2, dark="#111827", light="#ffffff")
        return qr_path

    def _run(self) -> None:
        try:
            ensure_runtime_directories()
            os.makedirs(os.path.dirname(CONV_DB_PATH), exist_ok=True)
            init_db()
            log.setLevel(logging.DEBUG)
            client = NewClient(NEO_DB_PATH)
            self._client = client

            @client.event(ConnectedEv)
            def handle_connected(client: NewClient, connected: ConnectedEv):
                client.send_presence(presence=Presence.AVAILABLE)
                self._set_status(
                    state="connected",
                    connected=True,
                    qr_available=False,
                    qr_path=None,
                    last_error=None,
                )

            @client.event(DisconnectedEv)
            def handle_disconnected(client: NewClient, disconnected: DisconnectedEv):
                self._set_status(state="disconnected", connected=False)

            @client.event(LoggedOutEv)
            def handle_logged_out(client: NewClient, logged_out: LoggedOutEv):
                self._set_status(
                    state="logged_out",
                    connected=False,
                    qr_available=False,
                    qr_path=None,
                )

            @client.event(HistorySyncEv)
            def handle_history(client: NewClient, history: HistorySyncEv):
                self._set_status(
                    state="connected",
                    connected=True,
                    qr_available=False,
                    qr_path=None,
                    last_error=None,
                )
                on_history_sync(client, history)

            @client.event(MessageEv)
            def handle_message(client: NewClient, message: MessageEv):
                try:
                    self._set_status(
                        state="connected",
                        connected=True,
                        qr_available=False,
                        qr_path=None,
                        last_error=None,
                        phone_hint=message.Info.MessageSource.Chat.User,
                    )
                except Exception:
                    pass
                on_message(client, message)

            @client.qr
            def handle_qr(client: NewClient, qr_data: bytes):
                try:
                    qr_path = self._write_qr_svg(qr_data)
                    self._set_status(
                        state="awaiting_qr_scan",
                        connected=False,
                        qr_available=True,
                        qr_path=qr_path,
                        last_error=None,
                    )
                except Exception as exc:
                    logging.exception(exc)
                    self._set_status(last_error=str(exc), state="error")

            self._set_status(state="starting", connected=False, last_error=None)
            client.connect()

            while not self._stop_requested:
                self._refresh_client_state()
                time.sleep(1)

        except Exception as exc:
            logging.exception(exc)
            self._set_status(state="error", connected=False, last_error=str(exc))
        finally:
            self._client = None
            if not self._stop_requested:
                self._set_status(connected=False)


runtime = WhatsAppRuntime()
