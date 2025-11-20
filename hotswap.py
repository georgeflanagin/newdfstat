# -*- coding: utf-8 -*-
import typing
from   typing import *

"""
There are two components in this module:

    reload_module -- reloads something you can import.
    HotSwap -- a class wrapper around a function to reload.
"""

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
import importlib
import logging
from   logging import CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET
import signal
import threading
import time

###
# Installed libraries like numpy, pandas, paramiko
###

###
# From hpclib
###
from   urlogger import URLogger

###
# imports and objects that were written for this project.
###

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


@trap
def reload_module(module):
    """
    Recursively reload a module and its submodules.
    """
    try:
        importlib.reload(module)
        logger.debug(f'Reloaded {module}')
    except Exception as e:
        logger.debug(f'Failed to reload {module} {e=}')


    # If analyses has submodules like analyses.utils, analyses.processors, etc.
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type(sys)) and attr.__name__.startswith(module.__name__ + '.'):
            reload_module(attr)



class HotSwap:
    """Manages a function living inside a module, with safe reload."""
    def __init__(self, module_name: str, func_name: str = "analyze_data"):
        self._module_name = module_name
        self._func_name = func_name
        self._lock = threading.RLock()
        self._module = None
        self.func = None  # current callable
        self.version = 0
        self.load(initial=True)


    def load(self, initial=False):
        with self._lock:
            try:
                if initial or self._module_name not in sys.modules:
                    logger.info("Importing %s", self._module_name)
                    self._module = importlib.import_module(self._module_name)
                else:
                    logger.info("Reloading %s", self._module_name)
                    importlib.invalidate_caches()
                    self._module = importlib.reload(self._module)

                new_func = getattr(self._module, self._func_name)
                if not callable(new_func):
                    raise TypeError(f"{self._module_name}.{self._func_name} is not callable")

                # Optional: verify signature/contract here if you like
                self.func = new_func  # atomic swap
                self.version += 1
                logger.info("Activated %s.%s (version %d)",
                         self._module_name, self._func_name, self.version)

            except Exception as e:
                # Keep previous version running; just log the failure.
                if initial:
                    raise  # no previous version to keep
                logger.exception("Reload FAILED; keeping previous version: %s", e)

    def __call__(self, *args, **kwargs):
        # No lock here: we want fast calls; assignment of self.func is atomic.
        f = self.func
        return f(*args, **kwargs)

