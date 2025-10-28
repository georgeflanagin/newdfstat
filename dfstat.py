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
import getpass
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET
import pickle
import signal
import time

###
# Installed libraries like numpy, pandas, paramiko
###
import pandas

###
# From hpclib
###
from   dorunrun import dorunrun
import linuxutils
from   sloppytree import deepsloppy, SloppyTree
from   urdecorators import trap
from   urlogger import URLogger

###
# imports and objects that were written for this project.
###
from   dfdb import DFDB

###
# Global objects
###
mynetid = getpass.getuser()
logger = None
logins = None
myargs = None

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

#########################################################
# Order of appearance of the functions:
#
# 1. Event handler
# 2. Other functions in alpha order.
# 3. main
#########################################################

@trap
def handler(signum:int, stack:object=None) -> None:
    """
    Map SIGHUP and SIGUSR1 to a restart/reload, and
    SIGUSR2 and the other common signals to an orderly
    shutdown.
    """
    global logger
    global myargs

    if signum in [ signal.SIGHUP, signal.SIGUSR1 ]:
        dfstat_main(myargs)

    elif signum in [ signal.SIGUSR2, signal.SIGQUIT, signal.SIGTERM, signal.SIGINT ]:
        logger.info(f'Closing up from signal {signum}')
        fileutils.fclose_all()
        sys.exit(os.EX_OK)

    else:
        return


@trap
def collect_data(login:str) -> int:
    global konstants

    return dorunrun(f'{login} {konstants.remote_script}', return_datatype=int)


@trap
def retrieve_data(logins:list) -> SloppyTree:
    global konstants

    facts = SloppyTree()
    localname=os.path.basename(konstants.remote_file)

    for login in logins:
        host=login.split('@')[-1]
        dorunrun(f"scp {login}:{konstants.remote_file} {host}.{localname}")
        facts[host] = deepsloppy(pickle.load(open(f"{host}.{localname}", 'rb')))

    return facts


@trap
def record_data(facts:SloppyTree, db:DFDB) -> int:
    """
    Return the number of records written.
    """
    i = 0
    facts = deepsloppy({k:v for k,v in facts.items() if k != 'time'})
    for h, val in facts.items():
        for k, v in val.items():
            db.add_row(h, k, v.total, v.used)
            i += 1

    return i


@trap
def dfstat_main(myargs:argparse.Namespace) -> int:

    global logger
    global logins
    global konstants

    if not os.path.isfile(myargs.db):
        logger.error(f"{myargs.db} not found.")
        print("Cannot find {myargs.db} to open it.")
        return os.EX_CONFIG

    db = DFDB(myargs.db)
    logins = db.get_logins()
    konstants = SloppyTree(db.get_constants())

    # Trap all the signals that we can trap.
    for _ in range(signal.SIGRTMIN):
        try:
            signal.signal(_, handler)
        except:
            pass

    # If we are running interactively, allow control-c and HUP.
    if os.isatty(0):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGHUP, signal.SIG_DFL)


    while True:
        ###
        # run the data collection program everywhere.
        ###
        pids = set()
        for login in logins:
            if (pid := os.fork()):
                pids.add(pid)
                logger.debug(f"created child {pid}")
                continue

            try:
                result = collect_data(login)
            except:
                result = 1
            finally:
                os._exit(result)


        while pids:
            child_pid, exit_status, usage = os.wait3(0)
            pids.remove(child_pid)
            logger and logger.info(f"{child_pid} finished with {exit_status=}")


        # Go get the data.
        facts = retrieve_data(logins)

        # Put it in the database.
        record_data(facts, db)

        # Play it safe, and run the analysis async.
        if (pid := os.fork()):
            pass
        else:
            try:
                analyze_data(db)
            finally:
                os._exit(os.EX_OK)

        # And go at it again.
        time.sleep(konstants.sample_rate*60)

    return os.EX_OK


if __name__ == '__main__':

    here       = os.getcwd()
    progname   = os.path.basename(__file__)[:-3]
    logfile    = f"{here}/{progname}.log"
    lockfile   = f"{here}/{progname}.lock"

    parser = argparse.ArgumentParser(prog="dfstat",
        description="What dfstat does, dfstat does best.")

    parser.add_argument('--db', type=str, default='dfstat.db')

    parser.add_argument('--log-level', type=int, default=INFO,
        choices=(CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET),
        help=f"Logging level, defaults to {logging.INFO}")

    parser.add_argument('-o', '--output', type=str, default="",
        help="Output file name")

    parser.add_argument('-z', '--zap', action='store_true',
        help="Remove old log file and create a new one.")

    myargs = parser.parse_args()
    if myargs.zap:
        try:
            unlink(logfile)
        except:
            pass


    logger = URLogger(logfile=logfile, level=myargs.log_level)

    with linuxutils.LockFile(lockfile):
        try:
            outfile = sys.stdout if not myargs.output else open(myargs.output, 'w')
            with contextlib.redirect_stdout(outfile):
                sys.exit(globals()[f"{progname}_main"](myargs))

        except Exception as e:
            print(f"Escaped or re-raised exception: {e}")

