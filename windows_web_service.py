"""Windows service host for the FastAPI web frontend."""

from __future__ import annotations

import json
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import servicemanager
import uvicorn
import win32event
import win32service
import win32serviceutil

from toolkit.utils import get_output_root


WORKSPACE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = get_output_root()
CONFIG_PATH = OUTPUT_DIR / "web_service_config.json"
LOG_PATH = OUTPUT_DIR / "web_service.log"
ERROR_LOG_PATH = OUTPUT_DIR / "web_service_error.log"

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "access_log": False,
}


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_service_config() -> dict:
    ensure_output_dir()
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
    except Exception:
        return dict(DEFAULT_CONFIG)

    config = dict(DEFAULT_CONFIG)
    if isinstance(payload, dict):
        config.update(payload)
    config["port"] = int(config.get("port", DEFAULT_CONFIG["port"]))
    config["access_log"] = bool(config.get("access_log", DEFAULT_CONFIG["access_log"]))
    return config


def configure_logging() -> logging.Logger:
    ensure_output_dir()
    logger = logging.getLogger("document_correction_toolkit.web_service")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    info_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    info_handler.setFormatter(formatter)
    logger.addHandler(info_handler)

    error_handler = RotatingFileHandler(ERROR_LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


class ToolkitWebService(win32serviceutil.ServiceFramework):
    _svc_name_ = "DocumentCorrectionToolkitWeb"
    _svc_display_name_ = "Document Correction Toolkit Web"
    _svc_description_ = "Hosts the Document Correction Toolkit web UI in the background."

    def __init__(self, args):
        super().__init__(args)
        self.h_wait_stop = win32event.CreateEvent(None, 0, 0, None)
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.logger = configure_logging()

    def SvcStop(self):
        self.logger.info("Stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.server is not None:
            self.server.should_exit = True
            self.server.force_exit = True
        win32event.SetEvent(self.h_wait_stop)

    def SvcDoRun(self):
        self.logger.info("Service starting")
        servicemanager.LogInfoMsg(f"{self._svc_name_} starting")
        try:
            self.main()
        except Exception:
            self.logger.exception("Service crashed")
            raise
        finally:
            self.logger.info("Service stopped")
            servicemanager.LogInfoMsg(f"{self._svc_name_} stopped")

    def main(self):
        config = load_service_config()
        self.logger.info("Using service config host=%s port=%s access_log=%s", config["host"], config["port"], config["access_log"])

        from local_web import app

        uvicorn_config = uvicorn.Config(
            app,
            host=config["host"],
            port=config["port"],
            reload=False,
            access_log=config["access_log"],
            log_config=None,
        )
        self.server = uvicorn.Server(uvicorn_config)
        self.server_thread = threading.Thread(target=self.server.run, name="uvicorn-service", daemon=True)
        self.server_thread.start()

        while True:
            wait_result = win32event.WaitForSingleObject(self.h_wait_stop, 1000)
            if wait_result == win32event.WAIT_OBJECT_0:
                break
            if self.server_thread is not None and not self.server_thread.is_alive():
                if self.server.started:
                    self.logger.info("Uvicorn exited normally")
                else:
                    raise RuntimeError("Uvicorn exited before signaling startup. Check port availability and logs.")
                break

        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread is not None:
            self.server_thread.join(timeout=30)
            if self.server_thread.is_alive():
                self.logger.warning("Uvicorn thread did not exit within timeout")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ToolkitWebService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ToolkitWebService)