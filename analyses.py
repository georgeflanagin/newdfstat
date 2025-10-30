# -*- coding: utf-8 -*-
import typing
from   typing import *

###
# Standard imports, starting with os and sys
###
min_py = (3, 9)
import os
import sys
if sys.version_info < min_py:
    print(f"This program requires Python {min_py[0]}.{min_py[1]}, or higher.")
    sys.exit(os.EX_SOFTWARE)

###
# Other standard distro imports
###
from   collections.abc import *
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET

###
# Installed libraries like numpy, pandas, paramiko
###
import pandas
import numpy as np
import statsmodels.api as sm

# Use Kwiatkowski-Phillips-Schmidt-Shin (KPSS) test
# to determine if the data is stationary
# if p-value of the test is less than 0.05, then
# the data isn't stationary (it has significant changes)
# and, hence, hpc@richmond.edu needs to be informed.
from statsmodels.tsa.stattools import kpss
from statsmodels.tsa.stattools import adfuller

###
# From hpclib
###
import linuxutils
from   urdecorators import trap
from   urlogger import URLogger

###
# imports and objects that were written for this project.
###
from   dfdb import DFDB

###
# Global objects
###
logger = URLogger.get_top_logger()

###
# Credits
###
__author__ = 'George Flanagin'
__copyright__ = 'Copyright 2025, University of Richmond'
__credits__ = None
__version__ = 0.1
__maintainer__ = 'George Flanagin'
__email__ = 'gflanagin@richmond.edu'
__status__ = 'in progress'
__license__ = 'MIT'

def run(db:DFDB) -> int:
    logger.debug('running analyses')
    data = db.get_data()


