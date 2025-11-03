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
import argparse
from   collections.abc import *
import contextlib
import datetime
import getpass
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET

###
# Installed libraries like numpy, pandas, paramiko
###
try:
    import pandas
    use_pandas=True
except:
    use_pandas=False

###
# From hpclib
###
import linuxutils
from   sqlitedb import SQLiteDB
from   urdecorators import trap
from   urlogger import URLogger

###
# imports and objects that were written for this project.
###

###
# Global objects
###
mynetid = getpass.getuser()
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


class DFDB (SQLiteDB):

    ADD_FILLDATE = """INSERT INTO filldates (
        host, mountpoint, filldate )
        VALUES (?, ?, ?)"""

    ADD_ROW = """INSERT INTO stats (
        host, mountpoint, total, used )
        VALUES (?, ?, ?, ?)"""

    GET_CONSTANTS = """SELECT * FROM konstants"""

    GET_DATA = """SELECT * FROM recent_stats"""

    GET_FILLDATES = """SELECT * FROM filldates_view"""

    GET_LOGINS = """SELECT * FROM logins"""

    def __init__(self, name:str) -> None:
        super().__init__(name, use_pandas=use_pandas)


    def add_filldate(self, host:str, mountpoint:str,
        filldate:datetime.datetime) -> int:

        return self.execute_SQL(DFDB.ADD_FILLDATE,
            host, mountpoint, filldate)


    def add_row(self, host:str, mountpoint:str, total:int, used:int) -> int:
        """
        Append a reading of disk space.
        """
        return self.execute_SQL(DFDB.ADD_ROW, host, mountpoint, total, used)


    def get_constants(self) -> dict:
        """
        Column names are the keys.
        """
        df=self.execute_SQL(DFDB.GET_CONSTANTS)
        return dict(zip(df.columns.tolist(), df.iloc[0].tolist()))


    def get_data(self) -> pandas.DataFrame:
        """
        Retrieve rows for analysis.
        """
        return self.execute_SQL(DFDB.GET_DATA)


    def get_filldates(self) -> pandas.DataFrame:
        """
        Retrieve our projections for the discs filling.
        """
        return self.execute_SQL(DFDB.GET_FILLDATES)


    def get_logins(self) -> pandas.DataFrame:
        """
        The remote logins are stored in the database.
        """
        df = self.execute_SQL(DFDB.GET_LOGINS)
        return df['login'].tolist()
