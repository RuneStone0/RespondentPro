#!/usr/bin/env python3
"""
Centralized logging configuration for the application.
Provides consistent logging setup across all modules.
"""

import logging
import os
import sys
from typing import Optional


def get_log_level_from_env() -> int:
    """
    Get log level from LOG_LEVEL environment variable.
    
    Returns:
        int: Logging level constant (defaults to logging.INFO)
    """
    log_level_str = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Map string values to logging constants
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    
    log_level = level_map.get(log_level_str, logging.INFO)
    
    # Log a warning if invalid value was provided
    if log_level_str not in level_map:
        # Use basicConfig to ensure we can log this warning
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stderr
        )
        logging.warning(
            f"Invalid LOG_LEVEL value '{os.environ.get('LOG_LEVEL')}'. "
            f"Valid values are: DEBUG, INFO, WARNING, ERROR, CRITICAL. "
            f"Defaulting to INFO."
        )
    
    return log_level


def setup_logging(force: bool = False) -> None:
    """
    Configure logging for the application.
    
    This function sets up a consistent logging configuration that works
    in both Cloud Functions and local development environments.
    
    Args:
        force: If True, reconfigure logging even if handlers already exist.
               Defaults to False (idempotent behavior).
    
    The configuration:
    - Uses StreamHandler to stderr (works for Cloud Functions and local dev)
    - Sets log level from LOG_LEVEL environment variable (defaults to INFO)
    - Uses consistent formatter across all modules
    - Ensures proper propagation for child loggers
    """
    root_logger = logging.getLogger()
    
    # Check if logging is already configured (unless force is True)
    if not force and root_logger.handlers:
        # Logging already configured, just ensure level is set correctly
        log_level = get_log_level_from_env()
        root_logger.setLevel(log_level)
        return
    
    # Get log level from environment variable
    log_level = get_log_level_from_env()
    
    # Remove any existing handlers if force is True
    if force:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    # Create StreamHandler to stderr (works for both Cloud Functions and local dev)
    handler = logging.StreamHandler(sys.stderr)
    
    # Set consistent formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(handler)
    
    # Set root logger level
    root_logger.setLevel(log_level)
    
    # Ensure child loggers propagate to root logger
    root_logger.propagate = False  # We handle it at root level
    
    # Log the configuration (if level allows)
    if log_level <= logging.INFO:
        logging.info(f"Logging configured with level: {logging.getLevelName(log_level)}")
