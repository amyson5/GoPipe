import sys
import threading
import time
from queue import Queue

import pandas as pd

from engine import GtpEngine
from localEngine import LocalEngine
from ikatagoEngine import IkatagoEngine
from logger import logger
from config import config

pipe_config = config["PIPE"]


class GtpPipe:
    def __init__(self, engine_ids=[], local=True) -> None:
        self.local = local
        self.engine_ids = [str(i) for i in engine_ids]
        self.engines: list[GtpEngine] = []
        self.message_queue = Queue()
        self.logger = logger

        self.init_game()

        self._lock = threading.Lock()
        self.message_loop_thread = None
        self.engine_monitor_thread = None

        self.start()

    def init_game(self):
        self.winrates = []
        self.scoreLead = []
        self.move_counts = 0
        self.komi = 7.5

        # time related
        self.lag_buffer = pipe_config.getfloat("lag_buffer", 1)
        self.max_time = 13
        self.response_time_limit = pipe_config.getfloat("response_time_limit", 5)

        # turn related
        self.my_turn = None
        self.my_turn_times = []
        self.opponent_turn_start = None
        self.opponent_turn_times = []

        self.max_visits = 10000
        self.top_visits = pipe_config.getint("top_visits", 200000)
        self.resign_threshold = pipe_config.getfloat("resign_threshold", 0.1)
        self.resign_consec_turn = pipe_config.getint("resign_consec_turn", 3)

        self.analysis: dict = {}

        self.commands_send: list = []

    def start(self):
        if self.local:
            local_engine = LocalEngine()
            local_engine.start()
            self.engines.append(local_engine)

        for engine_id in self.engine_ids:
            self.append_engine(engine_id)

        self.message_loop_thread = threading.Thread(
            target=self._message_loop_thread, daemon=True
        ).start()
        self.engine_monitor_thread = threading.Thread(
            target=self._engine_monitor_thread, daemon=True
        ).start()

    def append_engine(self, engine_id):
        try:
            if engine_id == str(0):
                engine = LocalEngine()
            elif engine_id == 'i':
                engine = IkatagoEngine()
            else:
                engine = GtpEngine(engine_id)
            engine.start()
            # sync queue after start, in case there are new cmds during starting.
            with self._lock:
                if self.commands_send:
                    for cmd in self.commands_send:
                        engine(cmd)
            if engine_id == str(0):
                self.engines.insert(0, engine)
            else:
                self.engines.append(engine)
            self.logger.info(f"{engine.engine_id} is appended")
        except Exception as e:
            self.logger.error(f"Exception when start {engine_id}:\n{e}")

    def stop_engine(self, engine_id):
        for engine in self.engines:
            if engine.engine_id == engine_id:
                engine.stop()
                self.engines.remove(engine)

    def __call__(self, gtp_command) -> None:
        self.message_queue.put(gtp_command)

    def _engine_monitor_thread(self):
        while not self.my_turn:
            for engine in self.engines:
                if not engine.is_alive():
                    self.engines.remove(engine)
                    self.logger.warning(f"Engine {engine.engine_id} stoped.")
                    # self.append_engine(engine.engine_id)
            time.sleep(5)

    def _message_loop_thread(self):
        while True:
            gtp_command = self.message_queue.get()
            try:
                self.logger.debug(f"Message Loop Received {gtp_command}")
                self.dealing_with_command(gtp_command)
            except Exception as e:
                self.logger.error(f"Exception in processing message {gtp_command}: {e}")

    def dealing_with_command(self, command):
        if "genmove" in command:
            self.dealing_with_genmove(command)
            return

        if "set_top_visits" in command:
            try:
                _, value = command.split()
                value = int(value)
                self.set_top_visits(value)
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}: {e}")
            return

        if "set_resign_threshold" in command:
            try:
                _, threshold = command.split()
                threshold = float(threshold)
                self.set_resign_threshold(threshold)
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}: {e}")
            return

        if "add_lag_buffer" in command:
            try:
                _, seconds = command.split()
                self.add_lag_buffer(seconds)
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}: {e}")
            return

        if "append_engine" in command:
            try:
                _, engine_id = command.split()
                self.append_engine(engine_id)
                return
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}: {e}")

        if "stop_engine" in command:
            try:
                _, engine_id = command.split()
                self.stop_engine(engine_id)
                return
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}: {e}")

        if "time_left" in command:
            try:
                cmd_id = command.split()[0]
                response = f"={cmd_id}"
                self.send_pseudo_response(response)
                return
            except Exception as e:
                self.logger.error(f"Exception when dealing command {command}, {e}")

        if "time_settings" in command:
            id, cmd, maint, byot, stone = command.strip().split()
            self.max_time = float(byot) - self.lag_buffer
            response = f"={id}"
            self.send_pseudo_response(response)
            return

        if "komi" in command:
            try:
                komi = command.split()[-1]
                komi = float(komi)
                self.set_komi(komi)
            except Exception as e:
                self.logger.error(f"Exception when set komi to {komi}: {e}")

        if "clear_board" in command:
            self.init_game()

        id, *_ = command.split()
        response = f"={id}"
        self.send_pseudo_response(response)
        self.send_command_to_engines(command)

    def send_command_to_engines(self, command: str):
        if "play" in command:
            self.move_counts += 1

        if "analyze" not in command:
            self.commands_send.append(command)

        for engine in self.engines:
            try:
                engine(command)
                self.logger.debug(f"Sending command {command} to {engine.engine_id}")
            except Exception as e:
                self.logger.error(
                    f"Exception when sending command {command} to {engine.engine_id}: {e}"
                )

    def resignp(self):
        if len(self.winrates) < 20:
            return False
        init_winrate = self.winrates[0]
        tail_winrates = self.winrates[-self.resign_consec_turn :]
        last_winrate = self.winrates[-1]
        if (
            last_winrate / init_winrate < 0.25
            and max(tail_winrates) < self.resign_threshold
            and (min(tail_winrates) == last_winrate)
        ):
            return True
        return False

    def send_pseudo_response(self, line: str):
        line = line.strip()
        response = f"{line}\n\n"
        print(response)
        sys.stdout.flush()
        self.logger.debug(f"Pipe send resoponse {response}")

    def update_engine_list(self):
        alive_engines = []
        for engine in self.engines:
            if engine.is_alive():
                alive_engines.append(engine)
        self.engines = alive_engines

    @property
    def alive_engines(self):
        self.update_engine_list()
        return self.engines

    def set_top_visits(self, value: int):
        self.top_visits = int(value)
        self.logger.debug(f"set top visits to {self.top_visits}")

    def set_resign_threshold(self, value: float):
        value = float(value)
        self.resign_threshold = value
        self.logger.debug(f"set resign threshold to {self.resign_threshold}")

    def add_lag_buffer(self, sec):
        additional_lag_buffer = float(sec)
        self.max_time = self.max_time - additional_lag_buffer
        self.lag_buffer += additional_lag_buffer
        self.logger.debug(f"set lag buffer to {self.lag_buffer}")

    def set_komi(self, value: float):
        value = float(value)
        self.komi = value
        self.logger.debug(f"Set komi to {self.komi}")
        if self.komi == 0.0:
            self.set_resign_threshold(0.05)

    def dealing_with_genmove(self, command):
        self.my_turn = True
        start = time.time()
        deadline = start + self.max_time
        response_deadline = start + self.response_time_limit

        self.adjust_max_visits()

        id, _, player = command.strip().split()

        self.analysis = {}
        result = pd.DataFrame()

        for engine in self.engines:
            engine.analysis = None

        self.request_analysis(player)

        while True:
            for engine in self.engines:
                if engine.analysis is not None:
                    self.analysis[engine.engine_id] = engine.analysis

            if len(self.analysis) > 0:  # == len(self.engines):
                try:
                    result = pd.concat(self.analysis.values())

                    total_visits = result.visits.sum()

                    if total_visits >= self.max_visits:
                        break

                except Exception as e:
                    self.logger.debug(f"Exception when reveiving analysis: {e}")

            if len(result) == 0:
                if time.time() > response_deadline:
                    self.request_analysis(player)
                    response_deadline += self.response_time_limit
                    self.logger.warning(f"Response deadling reached.")

            if time.time() >= deadline:
                if len(result) > 0:
                    break
                else:
                    deadline += self.max_time
                    self.logger.warning(f"Deadline reached.")

            time.sleep(0.1)

        move = self.move_from_df(result)
        time_used = time.time() - start

        # send a response instead of engine
        response = f"={id} {move}"
        self.send_pseudo_response(response)

        persudo_command = f"play {player} {move}\n"
        self.send_command_to_engines(persudo_command)

        # turn tracking
        if self.opponent_turn_start:
            opponent_turn_time = start - self.opponent_turn_start
            self.opponent_turn_times.append(opponent_turn_time)
        self.opponent_turn_start = time.time()
        turn_time = self.opponent_turn_start - start
        self.my_turn_times.append(turn_time)
        self.logger.debug(f"Turn time spend: {turn_time}")
        self.logger.debug(f"Max turn time spend: {max(self.my_turn_times)}")
        self.my_turn = False

        # move info
        responsed_engines = self.analysis.keys()
        self.logger.info(f"Visits: {total_visits}")
        self.logger.info(f"Time used: {time_used}")
        self.logger.debug(f"Received analysis from {responsed_engines}")
        self.logger.info(f"Winrates: {self.winrates[-3:]}")
        self.logger.info(f"ScoreLead: {self.scoreLead[-3:]}")

    def move_from_df(self, result: pd.DataFrame):
        result["totalScore"] = result.visits * result.scoreLead
        result["totalWinrate"] = result.visits * result.winrate
        result["totalOrder"] = result.visits * result.order

        # sum visits
        result = (
            result.loc[:, ["visits", "totalScore", "totalWinrate", "totalOrder"]]
            .groupby(by=result.index)
            .sum()
        )

        result["avgScore"] = result.totalScore / result.visits
        result["avgWinrate"] = result.totalWinrate / result.visits
        result["avgOrder"] = result.totalOrder / result.visits

        # calculate average
        move = result.sort_values("avgOrder", ascending=True).index[0]

        winrate = result.at[move, "avgWinrate"]
        scoreLead = result.at[move, "avgScore"]
        self.winrates.append(round(winrate, 2))
        self.scoreLead.append(round(scoreLead, 2))

        if self.resignp():
            return "resign"

        return move

    def adjust_max_visits(self):
        # TODO: based on winrate and score
        if self.move_counts < 10:
            self.max_visits = self.top_visits / 10
        else:
            self.max_visits = self.top_visits

    def request_analysis(self, player, interval=50):
        analyze_command = f"kata-analyze {player} {interval}".strip()
        self.send_command_to_engines(analyze_command)
