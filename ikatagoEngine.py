import os
from queue import Queue
import shlex
import subprocess
import sys
import threading

import pandas as pd

from logger import logger
from config import config
from localEngine import LocalEngine

engine_config = config['IKATAGO']
USER_FOLDER = engine_config.get('data_folder')


class IkatagoEngine(LocalEngine):
    """Starts and communicates with the KataGo gtp engine"""

    def __init__(self) -> None:
        self.engine_id = 'i'
        self.username = engine_config.get('username', 'someone')
        self.password = engine_config.get('password', 'hard-to-guess')

        self.command_queue = Queue()
        self.katago_process = None
        self.read_katago_thread = None
        self.command_loop_thread = None
        self.shell = False
        self.logger = logger

        self.analysis = None

        self.set_command()

    def set_command(self):
        exe_file = engine_config.get('exe', 'ikatago.exe')
        exe = os.path.expanduser(os.path.join(USER_FOLDER, exe_file))

        gtp_cfg_file_name = engine_config.get('gtp_config_file')
        gtp_cfg_file = os.path.expanduser(
            os.path.join(USER_FOLDER, gtp_cfg_file_name))

        self.command = shlex.split(
            f'"{exe}" --platform all --username {self.username} --password {self.password} --kata-local-config "{gtp_cfg_file}"'
        )