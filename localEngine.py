import os
import shlex
import subprocess
import sys
import threading
import traceback
from queue import Queue

import pandas as pd

from logger import logger
from config import config
from engine import GtpEngine

engine_config = config["LOCAL"]
USER_FOLDER = engine_config.get("katago_folder")


class LocalEngine(GtpEngine):
    """Starts and communicates with the KataGo gtp engine"""

    def __init__(self) -> None:
        self.engine_id = str(0)
        self.katago_process = None

        self.command_queue = Queue()
        self.read_katago_thread = None
        self.command_loop_thread = None
        self._lock = threading.Lock()
        self.shell = False

        self.logger = logger
        self.analysis = None

        self.set_command()

    def set_command(self):
        exe_file = engine_config.get("exe", "katago.exe")
        exe = os.path.expanduser(os.path.join(USER_FOLDER, exe_file))

        gtp_cfg_file_name = engine_config.get("gtp_config_file")
        gtp_cfg_file = os.path.expanduser(os.path.join(USER_FOLDER, gtp_cfg_file_name))

        model_name = engine_config.get("model", "b40.bin.gz")
        model_file = os.path.expanduser(os.path.join(USER_FOLDER, model_name))

        self.command = shlex.split(
            f'"{exe}" gtp -model "{model_file}" -config "{gtp_cfg_file}"'
        )

    def start(self):
        try:
            self.logger.info(f"Starting {self.engine_id} with {self.command}")
            startupinfo = None
            if hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                # stop command box popups on win/pyinstaller
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.katago_process = subprocess.Popen(
                self.command,
                startupinfo=startupinfo,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=self.shell,
            )
        except Exception as e:
            self.logger.error(f"Starting {self.engine_id} failed: {e}")
            return
        self.read_katago_thread = threading.Thread(
            target=self._read_katago_thread, daemon=True
        )
        self.read_katago_thread.start()
        self.command_loop_thread = threading.Thread(
            target=self._command_loop_thread, daemon=True
        )
        self.command_loop_thread.start()

    def stop(self):
        command = "quit"
        self.send_command(command)
        self.katago_process = None
        self.logger.debug(f"stop engine {self.engine_id}.")

    def is_alive(self, os_error="", exception_if_dead=False) -> bool:
        ok = self.katago_process and self.katago_process.poll() is None
        if not ok and exception_if_dead:
            if self.katago_process:
                code = self.katago_process and self.katago_process.poll()
                if code == 3221225781:
                    self.logger.error("Engine missing DLL")
                else:
                    os_error += f"status {code}"
                    self.logger.error(f"Engine died unexpectedly, os error: {os_error}")
                self.katago_process = None
            else:
                self.logger.error(f"Engine died unexpectedly, os error: {os_error}")
        return ok

    def shutdown(self, finish=False):
        process = self.katago_process
        if process:
            self.katago_process = None
            process.terminate()
        if self.read_katago_thread:
            self.read_katago_thread.join()

    def _read_katago_thread(self):
        while self.is_alive():
            try:
                line: str = self.katago_process.stdout.readline().strip().decode()
            except OSError as e:
                self.logger.error(f"Can not read line: {e}")
                return

            if "Uncaught exception" in line:
                self.logger.error(f"Engine Failed: {line}")

            if not line:
                continue

            try:
                if "info move" in line:
                    self.analysis = self.analysis_to_df(line)
            except Exception as e:
                self.logger.error(
                    f"Unexpected exception {e} while processing Engine output {line[:20]}"
                )

    def send_command(self, command):
        try:
            self.katago_process.stdin.write(f"{command}\n".encode())
            self.katago_process.stdin.flush()
        except Exception as e:
            self.logger.error(f"Exception when sending command {command}, {e}")
