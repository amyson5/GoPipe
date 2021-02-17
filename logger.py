#!/usr/bin/env python3

import logging
import os
from datetime import datetime

from config import config

log_config = config['LOG']

LOG_FOLDER = log_config.get('log_folder')
log_filename = ''.join(str(datetime.now()).split(':'))
LOG_FILE = os.path.expanduser(os.path.join(
    LOG_FOLDER, f'{log_filename}.log'))
logging.basicConfig(level=logging.DEBUG,
                    filename=LOG_FILE,
                    datefmt='%Y/%m/%d %H:%M:%S',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(lineno)d - %(module)s - %(message)s')

logger = logging.getLogger(__name__)
