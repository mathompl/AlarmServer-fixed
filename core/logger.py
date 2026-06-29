import logging
import inspect
import sys
import os
import queue          # <-- zmienione
import config

level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

# ============================================================

rootpath = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__)) + '/'

class DispatchingFormatter:
    def __init__(self, formatters, default_formatter):
        self._formatters = formatters
        self._default_formatter = default_formatter

    def format(self, record):
        formatter = self._formatters.get(record.name, self._default_formatter)

        # Safe handling for records without extra fields
        if not hasattr(record, 's_filename'):
            record.s_filename = getattr(record, 'filename', 'unknown')
        if not hasattr(record, 's_line_number'):
            record.s_line_number = getattr(record, 'lineno', 0)
        if not hasattr(record, 's_function_name'):
            record.s_function_name = getattr(record, 'funcName', 'unknown')

        return formatter.format(record)


def start(logfile=None, loglevel=None):
    if loglevel is None:
        log_level = "INFO"
    else:
        log_level = str(loglevel).strip().upper()

    # Setup logging handler
    if logfile:
        try:
            handler = logging.FileHandler(logfile)
        except IOError:
            handler = logging.StreamHandler()
            print("Unable to open %s for writing" % logfile)
    else:
        handler = logging.StreamHandler()

    # Set formatter
    handler.setFormatter(DispatchingFormatter({
        'alarmserver': logging.Formatter(
            '%(asctime)s - %(levelname)s - %(s_filename)s:%(s_function_name)s@%(s_line_number)s: %(message)s',
            '%b %d %H:%M:%S'
        )},
        logging.Formatter('%(asctime)s - %(levelname)s: %(message)s', '%b %d %H:%M:%S'),
    ))

    # Add handler and set level
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level_map.get(log_level, logging.INFO))

    logger = logging.getLogger('alarmserver')
    logger.info("Logger initialized with level: %s", log_level)

    start.started = 1


# ====================== GLOBAL VARIABLES ======================
start.started = 0


# ====================== LOGGING FUNCTIONS ======================
def error(message):
    write(logging.ERROR, message)

def debug(message):
    write(logging.DEBUG, message)

def warning(message):
    write(logging.WARNING, message)

def info(message):
    write(logging.INFO, message)


def write(level, message):
    """Internal write function with caller info"""
    (frame, filename, line_number, function_name, lines, index) = inspect.getouterframes(inspect.currentframe())[2]
    if filename == __file__:
        (frame, filename, line_number, function_name, lines, index) = inspect.getouterframes(inspect.currentframe())[3]

    extra = {
        's_filename': filename.replace(rootpath, ''),
        's_line_number': line_number,
        's_function_name': function_name
    }

    if start.started:
        # Opróżnij kolejkę
        while not write.queue.empty():
            job = write.queue.get()
            logging.getLogger('alarmserver').log(job['level'], job['message'], extra=job['extra'])

        logging.getLogger('alarmserver').log(level, message, extra=extra)
    else:
        write.queue.put({'level': level, 'message': message, 'extra': extra})


# Initialize queue
write.queue = queue.Queue()   # <-- zmienione
