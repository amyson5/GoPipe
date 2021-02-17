#!/usr/bin/env python3

import configparser
from constants import CONFIG_FILE
import pathlib
import os

config = configparser.ConfigParser()
path = pathlib.Path(__file__).parent.absolute()
config.read(os.path.join(path, CONFIG_FILE))
