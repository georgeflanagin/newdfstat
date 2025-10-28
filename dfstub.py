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
import ast
from   datetime import datetime, timezone
import pickle
import pprint
import shutil

###
# From hpclib
###
from   sloppytree import SloppyTree

__author__ = 'George Flanagin'
__copyright__ = 'Copyright 2025, University of Richmond'
__credits__ = None
__version__ = 0.1
__maintainer__ = 'George Flanagin'
__email__ = 'gflanagin@richmond.edu'
__status__ = 'in progress'
__license__ = 'MIT'


def dfstub_main() -> int:
    result=SloppyTree()
    result.time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        data=shutil.disk_usage('/home')
        result.home.total=data.total
        result.home.used=data.used

    except FileNotFoundError as e:
        result.home.total = result.home.used = 0

    for s in ('/scratch', '/scr', '/data'):
        try:
            data=shutil.disk_usage(s)
            result.scratch.total=data.total
            result.scratch.used=data.used
            break

        except FileNotFoundError as e:
            pass

    else:
        result.scratch.total = result.scratch.used = 0

    result=ast.literal_eval(pprint.pformat(result, width=120))
    print(result)

    with open('/tmp/df.data', 'wb+') as f:
        f.write(pickle.dumps(result, pickle.DEFAULT_PROTOCOL))
        f.flush()

    return os.EX_OK


if __name__ == '__main__':
    progname   = os.path.basename(__file__)[:-3]
    sys.exit(globals()[f"{progname}_main"]())
