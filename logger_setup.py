# logger_setup.py
import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console(color_system="auto")

def setup_logger(name="tracker_logger", level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        logger.handlers.clear()
    
    logger.setLevel(level)
    handler = RichHandler(rich_tracebacks=True, console=console, markup=True)
    formatter = logging.Formatter("%(message)s") # Keep it clean for Rich
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False # Prevent double logging if root logger is also configured
    return logger

# Example usage in other files:
# from logger_setup import setup_logger
# logger = setup_logger(__name__)
# logger.info("This is an [bold green]INFO[/] message.")
# logger.error("This is an [bold red]ERROR[/] message!")