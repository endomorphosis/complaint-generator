"""
Unit tests for the lib.log module
"""
import logging
import pytest
from lib.log import init_logging, make_logger


class TestLogging:
    """Test cases for logging functionality"""
    
    def test_init_logging_function_exists(self):
        """Test that init_logging function exists"""
        assert callable(init_logging)
    
    def test_init_logging_accepts_level_parameter(self):
        """Test that init_logging accepts a level parameter"""
        # Should not raise an exception
        init_logging(level='INFO')
        init_logging(level='DEBUG')
        init_logging(level='WARNING')
        
    def test_make_logger_returns_logger(self):
        """Test that make_logger returns a logger object"""
        logger = make_logger('test_logger')
        assert isinstance(logger, logging.Logger)
        
    def test_make_logger_creates_named_logger(self):
        """Test that make_logger creates a logger with the correct name"""
        logger_name = 'test_module'
        logger = make_logger(logger_name)
        assert logger.name == logger_name
        
    def test_logger_can_log_messages(self):
        """Test that created logger can log messages"""
        logger = make_logger('test')
        # This should not raise an exception
        logger.info('Test message')
        logger.debug('Debug message')
        logger.warning('Warning message')
        
    def test_make_logger_creates_different_loggers(self):
        """Test that make_logger creates different loggers for different names"""
        logger1 = make_logger('test1')
        logger2 = make_logger('test2')
        assert logger1.name != logger2.name
        assert logger1.name == 'test1'
        assert logger2.name == 'test2'
