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
import warnings

###
# Installed libraries like numpy, pandas, paramiko
###
import pandas
import numpy as np
from   sklearn.linear_model import LinearRegression

# Use Kwiatkowski-Phillips-Schmidt-Shin (KPSS) test
# to determine if the data is stationary
# if p-value of the test is less than 0.05, then
# the data isn't stationary (it has significant changes)
# and, hence, hpc@richmond.edu needs to be informed.
from statsmodels.tsa.stattools import kpss
from statsmodels.tsa.stattools import adfuller
from statsmodels.tools.sm_exceptions import InterpolationWarning


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
# Global objects and actions
###
warnings.filterwarnings("ignore", category=InterpolationWarning)
logger = URLogger.get_top_logger()

###
# The dataframe is global so that we can avoid populating it
# more than once per analysis. If you write more of these,
# remember to check this to see if it "is not None".
df = None
db_konstants = None
g_freq = None

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
def is_flat(s:pandas.Series, capacity:float) -> bool:
    """
    Avoid testing series where the value does not change (significantly).

    return -- None for bad data, True for flat, False for changing.
    """
    global logger

    s = s.dropna().astype(float)
    if s.empty: return None

    span = (s.max() - s.min()) / capacity
    logger.info(f"{s.max()=} {s.min()=} {span=} {capacity=}")

    return span/capacity < 0.005



@trap
def kpss_analysis_by_column(db:DFDB, c:str='used') -> list:
    logger.debug('running analyses')

    global df, db_konstants, g_freq
    out = []
    populate_globals(db)

    for (host, mnt), s, size in kpss_grouper(df, c, return_capacity=True):
        if is_flat(s, size): continue

        try:
            s['used'] /= size
            stat, pval, lags, crit = kpss(s, regression="c", nlags="auto")
        except Exception as e:
            logger.debug(f"{e=}")

        # No reason to further examine ones that are not changing.
        if stat > db_konstants['kpss_level']:
            out.append({"host": host, "mountpoint": mnt,
                "kpss_stat": stat, "pvalue": pval, "lags": lags})

    return out


def kpss_grouper(
        df: pandas.DataFrame,
        value_col: str = "used",
        *,
        freq: str = None,
        megabytes: bool = True,
        return_capacity: bool = False,
    ) -> Iterator[Tuple[Tuple[str, str], pandas.Series, Optional[float]]]:
    """
    df -- the DataFrame retrieved from the database.
    value_col -- what we are triaging.
    freq -- default is the freq in the konstants table of the database.
    megabytes -- if we want to scale the numbers. Figures in the
        billions and trillions are too large for these analyses.
    return_capacity -- whether or not to return the "size" of the
        file system.

    yields:
      key: (host, mountpoint)
      s:   pandas.Series with DatetimeIndex, uniformly sampled
      cap: float capacity in MiB or None if you did not ask for it.
    """

    global logger

    if freq is None: freq = g_freq

    df = df.copy()

    # Robust datetime parsing (UTC) and drop rows with bad timestamps
    df["time"] = pandas.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"])

    # Coerce the value column to numeric (guards against stray strings)
    df[value_col] = pandas.to_numeric(df[value_col], errors="coerce")

    has_total = "total" in df.columns
    if has_total:
        df["total"] = pandas.to_numeric(df["total"], errors="coerce")

    for key, g in df.groupby(["host", "mountpoint"], sort=False):
        g = g.sort_values("time")

        # Optional capacity (take max if it varies; otherwise the single value)
        cap_mib = None
        if return_capacity and has_total and not g["total"].isna().all():
            cap = g["total"].max()
            if pandas.notna(cap):
                cap_mib = float(cap) / (1 << 20) if megabytes else float(cap)

        # Build the time series with a DatetimeIndex and regularize it
        s = (
            g.set_index("time")[value_col]
             .astype(float)
             .resample(freq).mean()
             .interpolate(limit_direction="both")
        )

        # Optional scaling (bytes -> MiB)
        if megabytes: s = s / (1<<20)

        yield (key, s, cap_mib if return_capacity else None)


@trap
def populate_globals(db) -> bool:
    """
    Determine if the globals are None, and then fill them.
    The return value is probably not necessary, but it is
    present to communicate if there is something to do.
    """
    global df, db_konstants, g_freq
    if any(_ is None for _ in (df, db_konstants, g_freq)):
        df = db.get_data()
        db_konstants = db.get_constants()

        # pandas uses figures like "5min", but the database
        # stores 5 as an integer.
        g_freq = db_konstants['sample_rate'] = str(db_konstants['sample_rate'])+"min"

        return True
    return False


@trap
def regression_analysis(db:DFDB, c:str='used', cases:list=None) -> dict:
    """
    Admittedly, it doesn't make much sense to regress on anything
    except space used, but I have likely overlooked many future
    uses when writing this code.
    """

    global logger
    global df, db_konstants, g_freq
    populate_globals(db)

    results = []

    for (host, mountpoint), s, fs_size in kpss_grouper(df, return_capacity=True):

        if cases is not None:
            if (host, mountpoint) not in cases: continue

        # logger.debug(f"{host} {mountpoint} {fs_size=} {s=}")

        t_days = (s.index - s.index[0]) / pandas.Timedelta(days=1)

        # Prepare X, y for regression
        X = t_days.to_numpy().reshape(-1, 1)
        y = s.to_numpy()

        model = LinearRegression().fit(X, y)
        slope = model.coef_[0]          # MiB per day
        intercept = model.intercept_
        r2 = model.score(X, y)

        if fs_size is not None and slope > 0:
            days_to_full = (fs_size - intercept) / slope

        results.append(dict(
            host=host, mountpoint=mountpoint,
            slope=slope, intercept=intercept, r2=r2, days_to_full=days_to_full
            ))

    # logger.debug(f"Regression {results=}")
    return results


@trap
def run(db:DFDB) -> None:
    populate_globals(db)

    # Only the interesting cases (i.e., unstable) are in the
    # result set.
    results = kpss_analysis_by_column(db)
    cases = list(tuple(_['host'], _['mountpoint']) for _ in results)
    results = regression_analysis(db, 'used', cases)
    for result in results:
        db.add_filldate(result['host'], result['mountpoint'], result['days_to_full'])



if __name__ == "__main__":
    try:
        os.unlink('analyses.log')
    except:
        pass

    logger = URLogger(logfile='analyses.log', level=logging.DEBUG)
    db = DFDB('dfstat.db')
    df = db.get_data()

    kpss_analysis_by_column(db)
    regression_analysis(db)

