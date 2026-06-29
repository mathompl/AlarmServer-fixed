#!/usr/bin/python
## Alarm Server
## Supporting Envisalink 2DS/3
## Contributors: https://https://github.com/mathompl/AlarmServer-fixed/
##
## This code is under the terms of the GPL v3 license.

# Python standard modules
import sys
if sys.version_info[0] >= 3:
    import http.client
    import urllib.request
    import urllib.parse
    sys.modules['httplib'] = http.client
    sys.modules['urllib2'] = urllib.request
    sys.modules['urlparse'] = urllib.parse

import getopt
import os
import glob
import importlib

# Alarm server modules
from core.config import config
from core.state import state
from core.events import events
from core import logger
from core import httpslistener
from core import envisalink
from core import envisalinkproxy

# TODO: move elsewhere
import tornado.ioloop


def load_plugins():
    currpath = os.path.dirname(os.path.abspath(__file__))
    plugins_dir = os.path.join(currpath, "plugins")
    
    if not os.path.isdir(plugins_dir):
        logger.warning("PLugins dir doesnt exits")
        return

    print("Loading plugins...")  # lub logger.info

    for filename in os.listdir(plugins_dir):
        if not filename.endswith('.py') or filename.startswith('__'):
            continue

        module_name = filename[:-3]  

        try:
            module = importlib.import_module(f"plugins.{module_name}")

            if hasattr(module, 'init') and callable(module.init):
                logger.debug(f"Loading plugin: {module_name}")
                module.init()
            else:
                logger.debug(f"Plugin {module_name} doesn't have init()")

        except Exception as e:
            logger.error(f"Error loading pluginu {module_name}: {e}")


def main(argv):
    print("-----------------------------------")
    print("Alarm server starting ...\n")

    # Set default config
    conffile = 'alarmserver.cfg'

    try:
        opts, args = getopt.getopt(argv, "c:", ["config="])
    except getopt.GetoptError:
        sys.exit(2)

    for opt, arg in opts:
        if opt in ("-c", "--config"):
            conffile = arg

    config.load(conffile)

    if config.LOGTOFILE:
        logger.start(logfile=config.LOGFILE, loglevel=config.LOGLEVEL)
    else:
        logger.start(loglevel=config.LOGLEVEL)

    # Debug konfiguracji
    logger.debug("=== FULL CONFIG DUMP ===")
    for attr in sorted(dir(config)):
        if attr.startswith('__') or attr.startswith('_'):
            continue
        try:
            value = getattr(config, attr)
            logger.debug(f"  {attr.ljust(25)} = {repr(value)}")
        except Exception:
            logger.debug(f"  {attr.ljust(25)} = <error>")
    logger.debug("========================")

    # Inicjalizacja
    state.init()
    state.setVersion(0.3)

    # Start komponentów
    alarmclient = envisalink.Client()
    alarmproxy = envisalinkproxy.Proxy()

    if config.HTTPS:
        httpsserver = httpslistener.start()

    if config.HTTP:
        httpserver = httpslistener.start(https=False)

    # Load plugins - NOWOCZESNA WERSJA
    load_plugins()

    # Start tornado ioloop
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main(sys.argv[1:])
