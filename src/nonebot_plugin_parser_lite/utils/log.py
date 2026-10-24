"""Logging adapter used by the standalone build."""

import logging


class ParserLogger(logging.LoggerAdapter):
    def success(self, message, *args, **kwargs) -> None:
        self.info(message, *args, **kwargs)


logger = ParserLogger(logging.getLogger("nonebot_plugin_parser_lite"), {})
