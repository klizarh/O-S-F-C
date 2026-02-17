"""Tests for the LogUtil logging wrapper."""

import logging
from LogUtil import get_logger


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger('test')
        assert isinstance(logger, logging.Logger)

    def test_logger_name_prefixed(self):
        logger = get_logger('TestModule')
        assert logger.name == 'mvp.TestModule'

    def test_default_name(self):
        logger = get_logger()
        assert logger.name == 'mvp.MvpLogger'

    def test_has_screen_handler(self):
        logger = get_logger('test_screen')
        handler_types = [type(h) for h in logger.handlers]
        assert logging.StreamHandler in handler_types

    def test_no_duplicate_handlers(self):
        """Calling get_logger twice should not add duplicate handlers."""
        name = 'test_no_dup'
        logger1 = get_logger(name)
        n_handlers = len(logger1.handlers)
        logger2 = get_logger(name)
        assert logger1 is logger2
        assert len(logger2.handlers) == n_handlers
