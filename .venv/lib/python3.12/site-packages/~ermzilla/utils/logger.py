"""Logging configuration for TermZilla."""

import logging
import sys
from pathlib import Path


def setup_logger(log_level: str = "INFO") -> logging.Logger:
    """Set up and return the application logger.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("termzilla")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (only if config dir exists)
    try:
        config_dir = Path.home() / ".config" / "termzilla"
        config_dir.mkdir(parents=True, exist_ok=True)
        log_file = config_dir / "termzilla.log"
        
        file_handler = logging.FileHandler(str(log_file))
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except OSError:
        pass  # Skip file logging if config dir is not writable
    
    return logger
