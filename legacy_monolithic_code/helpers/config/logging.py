"""
Logging configuration for the Turkish Sports News API.
"""

import logging
import os
import sys
from datetime import datetime

def configure_logging():
    """Configure logging for the application"""
    log_level_name = os.getenv('LOG_LEVEL', 'INFO')
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Log file named with current date
    log_file = os.path.join(log_dir, f'turkish_sports_news_api_{datetime.now().strftime("%Y%m%d")}.log')
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout), # Keep stdout for console
            logging.FileHandler(log_file, encoding='utf-8') # Specify UTF-8 for file
        ]
    )

    # For stdout, if it's a terminal that might not support UTF-8 by default on Windows
    # we can try to force it, or ensure the application is run in a UTF-8 compatible terminal.
    # A common approach is to reconfigure sys.stdout if necessary,
    # but for basic logging.StreamHandler, it often respects the environment.
    # If issues persist with stdout, one might need to wrap sys.stdout:
    # import codecs
    # sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    # However, for FileHandler, specifying encoding is standard.

    # Reconfigure StreamHandler for stdout to explicitly use UTF-8
    # This is important for Windows environments where default console encoding might not be UTF-8
    # Remove the old StreamHandler if basicConfig added one without explicit encoding control for stdout
    root_logger = logging.getLogger()
    # Remove existing StreamHandlers to avoid duplicate messages if basicConfig added one
    # This is a bit aggressive; a more nuanced approach might be needed if other handlers are configured elsewhere.
    # For simplicity here, we assume basicConfig is the primary configurator.
    
    # Find and remove default StreamHandler if it exists and re-add with UTF-8
    # This is safer than clearing all handlers if other handlers are expected.
    new_handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    for handler in root_logger.handlers[:]: # Iterate over a copy
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
            # If we want to replace it with a UTF-8 one
            # Forcing UTF-8 on sys.stdout can be tricky and environment-dependent.
            # Python 3.7+ generally handles Unicode to console better.
            # The most robust solution for console is ensuring the console itself is set to UTF-8 (e.g., chcp 65001 in cmd.exe)
            # or using a modern terminal like Windows Terminal.
            # For the logger, we can ensure the handler tries to encode in UTF-8.
            # However, direct encoding on StreamHandler is not as straightforward as FileHandler.
            # The primary issue is usually the terminal's display capability rather than logger's encoding.
            # The FileHandler is the one we can directly control for encoding.
            # The UnicodeEncodeError in the traceback points to the stream.write in logging,
            # which for console output, depends on sys.stdout.encoding.
            pass # Keep the original stdout handler from basicConfig, assuming environment handles it or it's less critical than file.
                 # If console output is still an issue, external configuration of the console (e.g. chcp 65001) or
                 # PYTHONIOENCODING=utf-8 environment variable is often the better fix.
        new_handlers.append(handler) # Keep other handlers (like the original FileHandler if it wasn't the one we're replacing)
                                     # Or, more simply, just ensure the FileHandler is UTF-8 and rely on basicConfig for stdout.

    # Simpler approach: basicConfig with FileHandler explicitly set to UTF-8.
    # The previous basicConfig call already added a StreamHandler for stdout.
    # We just need to ensure the FileHandler part is correct.
    # Let's refine the basicConfig call itself.

    # Corrected basicConfig setup:
    # Close existing handlers to reconfigure cleanly
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)
    
    # Setup handlers individually for more control
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # For StreamHandler, ensure it can handle UTF-8 output.
    # This often depends on the console/terminal's capabilities.
    # Python 3.7+ sys.stdout.reconfigure(encoding='utf-8') can be used in some contexts,
    # but it's safer to ensure the terminal itself is configured for UTF-8.
    # The PYTHONIOENCODING=utf-8 environment variable is a good general solution.
    stream_handler = logging.StreamHandler(sys.stdout) 
    stream_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Configure the root logger with the new handlers
    # logging.basicConfig is a convenience function that should ideally be called only once.
    # Since we are reconfiguring, we set the level and handlers on the root logger directly.
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    # Set specific levels for some loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return logging
