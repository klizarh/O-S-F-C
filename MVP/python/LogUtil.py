'''Wrapper for the Python Logger to add standard MVP customization
'''
import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_LEVEL = logging.INFO
FILE_LEVEL = logging.WARNING

# Resolve the MVP root directory.  Prefer the MVP_DIR environment variable;
# fall back to /home/pi/MVP for backwards-compatibility on the Pi.
MVP_DIR = os.environ.get('MVP_DIR', '/home/pi/MVP')
LOG_DIR = os.path.join(MVP_DIR, 'logs')

def get_logger(name="MvpLogger"):
    """Create and return a logger

    Builds a Python logger to:
      log everything to the screen
      WARNING to a rotating file (when the log directory exists)

    Args:
        name: The name given to the logger
    Returns:
        logger: the logger object
    Raises:
        None
    """
    fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    # build logger
    logger = logging.getLogger('mvp.'+name)
    logger.setLevel(LOG_LEVEL)

    # Only add handlers once (avoid duplicate messages on repeated calls)
    if logger.handlers:
        return logger

    # Rotating File handler - only send WARNING and above
    # Skip file handler when the log directory does not exist (e.g. in CI
    # or development environments that are not running on a Pi).
    if os.path.isdir(LOG_DIR):
        fname = os.path.join(LOG_DIR, 'mvp.log')
        file_handler = TimedRotatingFileHandler(fname, when="d", interval=30, backupCount=3)
        file_handler.setLevel(FILE_LEVEL)
        formater = logging.Formatter(fmt)
        file_handler.setFormatter(formater)
        logger.addHandler(file_handler)

    # Screen handler - display all (DEBUG, defaults above)
    screen_handler = logging.StreamHandler()
    screen_formater = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
    screen_handler.setFormatter(screen_formater)

    # Add handlers
    logger.addHandler(screen_handler)

    return logger


def test():
    """Test of the logger
    A light weight test, less complex that PyUnit

    Args:
        None
    Returns:
        None
    Raises:
        None
    """
    print ("Test MvpLogger")
    print ("Getting logger")
    logger = get_logger()
    print ("Testing output")
    logger.debug("Something happening here")
    logger.info("Just thought you might like to know")
    logger.warning("Will Robinson ...")

if __name__ == "__main__":
    test()
