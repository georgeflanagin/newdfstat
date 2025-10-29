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
import ast
from   collections.abc import *
import contextlib
import getpass
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET
import pickle
import signal
import sqlite3
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
def analyze_data(db:DFDB) -> int:
    """
    Take a look at the recent data, and send alerts as necessary.
    """
    return os.EX_OK


@trap
def assemble_data(logins:list) -> SloppyTree:
    """
    This function assumes there is something to collect, or at
    least *attempt* to connect on the remote computers. The argument
    is a global object -- it is passed as a parameter to assist with
    testing this function in isolation.

    The file adam:/tmp/dfdata becomes ~/adam.dfdata. The files are
    pickles, so everything we need to know is in them.
    """
    global konstants
    global logger

    facts = {}

    for login in logins:
        host=login.split('@')[-1]
        with open(f"{host}.dfdata") as f:
            s=f.read().strip()
            if not len(s): continue
            try:
                facts[host] = ast.literal_eval(s)
            except Exception as e:
                logger.error(f"{e=} {s=}")

    return facts


@trap
def collect_data(login:str) -> str:
    """
    Run the script on the remote computer. There is no useful return
    value other than that the attempt succeeded or failed.
    """
    global konstants
    global logger

    host=login.split('@')[-1]
    stubfile=konstants.remote_command.split()[-1]
    result = dorunrun(f'scp {stubfile} {login}:.')
    result = dorunrun(f'ssh {login} {konstants.remote_command}', timeout=10)
    ###
    # The return value is something like this:
    #
    # "{'home': {'total': 3914624106496, 'used': 813810130944},
    #   'scratch': {'total': 3914624106496, 'used': 813810130944},
    #   'time': '2025-10-28 16:28:06'}"
    ###
    logger.debug(f'data collection on {login} returned {result=}')
    with open(f"{host}.dfdata", 'w+') as f:
        f.write(result['stdout'])

    return result


@trap
def record_data(facts:SloppyTree, db:DFDB) -> int:
    """
    Return the number of records written.
    """
    i = j = 0
    for host, data in facts.items():
        for mountpoint in data:
            try:
                db.add_row(host, mountpoint,
                    facts[host][mountpoint]['total'], facts[host][mountpoint]['used'])
                i+=1
            except sqlite3.IntegrityError as e:
                j+=1

    logger.info(f'wrote {i} records to the database; {j} failures.')
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
    logger.info('database opened.')
    logins = db.get_logins()
    konstants = SloppyTree(db.get_constants())
    logger.info('global data retrieved.')

    # Trap all the signals that we can trap.
    for _ in range(signal.SIGRTMIN):
        try:
            signal.signal(_, handler)
        except:
            pass
    logger.debug('signals trapped.')

    # If we are running interactively, allow control-c and HUP.
    if os.isatty(0):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        logger.info('control-c restored.')

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
                collect_data(login)
                result = 0
            except:
                result = 1
            finally:
                os._exit(result)


        while pids:
            child_pid, exit_status, usage = os.wait3(0)
            pids.remove(child_pid)
            logger.debug(f"{child_pid} finished with {exit_status=}")


        # Go get the data.
        facts = assemble_data(logins)

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
        if os.isatty(0):
            break
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
            os.unlink(logfile)
        except Exception as e:
            pass


    logger = URLogger(logfile=logfile, level=myargs.log_level)

    with linuxutils.LockFile(lockfile):
        try:
            outfile = sys.stdout if not myargs.output else open(myargs.output, 'w')
            with contextlib.redirect_stdout(outfile):
                sys.exit(globals()[f"{progname}_main"](myargs))

        except Exception as e:
            print(f"Escaped or re-raised exception: {e}")

