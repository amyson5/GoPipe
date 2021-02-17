import paramiko
import sys
import threading
from queue import Queue

import pandas as pd

from logger import logger
from config import config

engine_config = config["ENGINE"]
USER_FOLDER = engine_config.get("data_folder")


class GtpEngine:
    def __init__(self, engine_id: str) -> None:
        self.engine_id = engine_id
        host, port, username, password = engine_config.get(
            engine_id).split("/")
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.command = "run-katago --transmit-move-num 6 -- gtp -override-config numSearchThreads=32"

        self.command_queue = Queue()

        self.read_katago_thread = None
        self.command_loop_thread = None
        self.logger = logger
        self.transport = None

        self.analysis = None

    def start(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=5,
                allow_agent=False,
                look_for_keys=False,
            )
            self.transport = self.client.get_transport()
            self.channel = self.transport.open_session(timeout=2)
            self.channel.exec_command(self.command)
            self.logger.debug(f"Start {self.engine_id} with {self.command}")
        except Exception as e:
            self.logger.error(f"Starting {self.engine_id} failed:\n{e}")
        self.read_katago_thread = threading.Thread(
            target=self._read_katago_thread, daemon=True
        )
        self.read_katago_thread.start()
        self.command_loop_thread = threading.Thread(
            target=self._command_loop_thread, daemon=True
        )
        self.command_loop_thread.start()

    def _read_katago_thread(self):
        while self.is_alive():
            if not self.channel.recv_ready():
                continue
            try:
                line: str = self.channel.makefile().readline().strip()
            except OSError as e:
                self.logger.error(f"Can not read line: {e}")
                return

            if not line:
                continue

            try:
                if "info move" in line:
                    if not line.startswith("info move"):
                        continue
                    self.analysis = self.analysis_to_df(line)
            except Exception as e:
                self.logger.error(
                    f"Unexpected exception {e} while processing Engine output {line[:20]}"
                )

    def __call__(self, command):
        self.command_queue.put(command)

    def _command_loop_thread(self):
        while self.is_alive():
            command = self.command_queue.get().strip()
            try:
                self.send_command(command)
            except Exception as e:
                self.logger.error(
                    f"Exception in processing command {command} with Engine {self.engine_id}:\n{e}"
                )

    def send_command(self, command):
        self.channel.sendall(f"{command}\n")

    def stop(self):
        self.client.close()

    def is_alive(self):
        return self.transport and self.transport.is_authenticated()

    def analysis_to_df(self, analysis: str) -> pd.DataFrame:
        moves = [move.strip().split()[:24]
                 for move in analysis.split("info ") if move]

        def list_to_dict(lst):
            i = iter(lst)
            return dict(zip(i, i))

        records = [list_to_dict(move) for move in moves]
        df = pd.DataFrame.from_records(records, index="move").astype("float")
        return df
