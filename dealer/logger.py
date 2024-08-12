import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name, log_file, level=logging.INFO):
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a custom logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create handlers
    c_handler = logging.StreamHandler()  # Console handler
    f_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)  # File handler
    
    # Create formatters and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    c_handler.setFormatter(formatter)
    f_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

    return logger

# Usage
logger = setup_logger('stock', './output/logs/app.log')