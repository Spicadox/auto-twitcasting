import logging
from logging.handlers import TimedRotatingFileHandler
import os.path
import const
import datetime


# Filter subclass that does not allow the file logging of sleeping messages
class NoParsingFilter(logging.Filter):
    previous_record = None
    count = 0

    def filter(self, record):
        return 'is currently offline' not in record.getMessage()


class DuplicateFilter(logging.Filter):
    previous_record = None
    count = 0

    def filter(self, record):
        record_matches = False
        if logging.getLogger().level == logging.DEBUG:
            if NoParsingFilter.previous_record is None:
                NoParsingFilter.previous_record = record.getMessage()
            elif record == NoParsingFilter.previous_record:
                NoParsingFilter.count += 1
                record_matches = True
            else:
                NoParsingFilter.count = 0
            if NoParsingFilter.count % 1000 == 0:
                record.message = "Filtered 1000 identical message"
        return not record_matches


def create_logger():
    # Check if log dir exist and if not create it
    logging.handlers.TimedRotatingFileHandler
    log_dir = os.getcwd()+"\\logs"
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)

    # Get the logger object
    logger = logging.getLogger(__name__)

    # If logger has already been created then return it(for the imported modules)
    if len(logger.handlers) != 0:
        return logger

    # Set logging level and log path
    logger.setLevel(logging.DEBUG)
    current_date = str(datetime.date.today()).replace("-", "")
    log_path = f"{log_dir}\\logfile.log"

    # Create a new log file everyday
    handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s [%(filename)s:%(lineno)d] %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M')
    handler.setFormatter(formatter)
    handler.suffix = "%Y%m%d"   # file suffix to be changed
    handler.addFilter(NoParsingFilter())

    # logging.basicConfig(level=logging.INFO,
    #                     format='%(asctime)s [%(filename)s:%(lineno)d] %(levelname)-5s %(message)s',
    #                     datefmt='%Y-%m-%d %H:%M',
    #                     filename=log_path)

    # define a Handler which writes DEBUG messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
    # tell the handler to use this format
    console.setFormatter(console_formatter)
    # add the handlers to the root logger
    logger.addHandler(console)
    logger.addHandler(handler)

    # If logging is not enabled then remove the root log handler but keep the stream handler
    if not const.LOGGING:
        try:
            lhStdout = logger.handlers[1]
            logger.removeHandler(lhStdout)
        except IndexError as ierror:
            logger.error(ierror)
            return logger
    return logger
