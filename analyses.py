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
import datetime
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET

###
# Installed libraries like numpy, pandas, paramiko
###
import pandas
import numpy as np
from sklearn.linear_model import LinearRegression

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
# The dataframe is global so that we can avoid populating it
# more than once per analysis. If you write more of these,
# remember to check this to see if it "is not None".
df = None
db_konstants = None
freq = None

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


@trap
def host_mount_grouper(df: pandas.DataFrame) -> pandas.DataFrame:
    """
    This is the most general generator/iterator. It
    yields sub frames for each host, mountpoint pair.

    yields -- a tuple with (host, mountpoint) and the matching,
        sorted rows corresponding to the (host, mountpoint) key.
    """
    df = df.copy()

    # Start with getting the times standardized in case
    # the format in the database changes.
    df['time'] = pandas.to_datetime(df['time'], errors='coerce', utc=True)

    for (host, mnt), g in df.groupby(['host', 'mountpoint'], sort=False):
        yield (host, mnt), g.sort_values("time").reset_index(drop=True)


@trap
def kpss_grouper(df: pandas.DataFrame, value_col:str="used") -> tuple:
    """
    This is a grouper specifically for columns undergoing
    kpss analysis. 'used' (the amount of disc space used) seems
    like the obvious default given that it increases as the
    disc fills.

    This function also cleans up the data and imputes missing
    values in the time series.
    """
    global freq

    df = df.copy()

    df["time"] = pandas.to_datetime(df["time"], errors="coerce", utc=True)
    for key, g in df.groupby(["host", "mountpoint"], sort=False):
        s = (
            g.sort_values("time")
             .set_index("time")[value_col]
             .resample(freq).mean()
             .interpolate(limit_direction="both")
            )
        yield key, s


@trap
def kpss_analysis_by_column(db:DFDB, c:str='used') -> pandas.DataFrame:
    logger.debug('running analyses')

    global df, db_konstants, freq
    out = []
    populate_globals()

    for (host, mnt), s in kpss_grouper(df, c):
        try:
            stat, pval, lags, crit = kpss(s, regression="c", nlags="auto")
        except Exception as e:
            logger.debug(f"{stat=}, {pval=}, {e=}")

        # No reason to further examine ones that are not changing.
        if stat > db_konstants['kpss_level']:
            out.append({"host": host, "mountpoint": mnt,
                    "kpss_stat": stat, "pvalue": pval, "lags": lags})

    out=pandas.DataFrame(out)
    out.to_csv(datetime.datetime.now().isoformat()+".csv")

    return out


@trap
def populate_globals(db) -> bool:
    """
    Determine if the globals are None, and then fill them.
    The return value is probably not necessary, but it is
    present to communicate if there is something to do.
    """
    global df, db_konstants, freq
    if any(_ is None for _ in (df, db_konstants, freq)):
        df = db.get_data()
        df['used'] /= df['total'].replace(0, np.nan)
        db_konstants = db.get_constants()

        # pandas uses figures like "5min", but the database
        # stores 5 as an integer.
        freq = db_konstants['sample_rate'] = str(db_konstants['sample_rate'])+"min"

        return True
    return False


@trap
def regression_analysis(db:DFDB, c:str='used') -> dict:
    """
    Admittedly, it doesn't make much sense to regress on anything
    except space used, but I have likely overlooked many future
    uses when writing this code.
    """

    global df, db_konstants, freq
    populate_globals()

    results = []

    for (host, mountpoint), s in host_mount_grouper(df):

        # t is the normalized days since the earliest reading.
        t = (s.index - s.index[0]).total_seconds() / 86400.0

        # -1 -> however long it is, 1 -> one column in this matrix.
        X = t.reshape(-1, 1)
        y = s[c].values
        model = LinearRegression().fit(X, y)
        slope = model.coef_[0]
        intercept = model.intercept_
        r2 = model.score(X, y)

        days_to_full = (1 - intercept) / slope if slope > 0 else np.inf
        results.append(dict(
            host=host, mountpoint=mountpoint,
            slope=slope, intercept=intercept, r2=r2, days_to_full=days_to_full
            ))

    return pandas.DataFrame(results)



run = kpss_analysis_by_column

if __name__ == "__main__":
    db = DFDB('dfstat.db')
    run(db)

