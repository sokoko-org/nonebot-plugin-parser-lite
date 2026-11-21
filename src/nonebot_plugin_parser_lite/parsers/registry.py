import asyncio

from nonebot import logger

from ..constants import PlatformEnum
from .base import BaseParser

__all__ = ["REGISTRY", "ParserRegistry"]


class ParserRegistry:
    """集中管理「已启用解析器」的类、实例与生命周期

    - :meth:`load` 按配置导入并记录启用的解析器类
    - 解析器实例按需惰性创建
    - :meth:`run_startup` / :meth:`aclose_all` 遍历所有解析器，调用其
      :meth:`BaseParser.on_startup` / :meth:`BaseParser.aclose`
    """

    def __init__(self) -> None:
        self._enabled_classes: list[type[BaseParser]] = []
        self._instances: dict[type[BaseParser], BaseParser] = {}
        self._keyword_class_map: dict[str, type[BaseParser]] = {}
        self._loaded = False

    def load(self) -> list[type[BaseParser]]:
        """导入并记录启用的解析器类（可重复调用，后一次覆盖前一次）"""
        from . import load_enabled_parsers

        self._enabled_classes = load_enabled_parsers()
        self._keyword_class_map = {
            rule.keyword: parser_cls
            for parser_cls in self._enabled_classes
            for rule in parser_cls._key_patterns
        }
        # 丢弃不再启用的已缓存实例，避免为已禁用平台返回旧实例
        enabled = set(self._enabled_classes)
        self._instances = {
            cls: inst for cls, inst in self._instances.items() if cls in enabled
        }
        self._loaded = True
        return self._enabled_classes

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    @property
    def enabled_classes(self) -> list[type[BaseParser]]:
        self._ensure_loaded()
        return self._enabled_classes

    @property
    def keyword_class_map(self) -> dict[str, type[BaseParser]]:
        self._ensure_loaded()
        return self._keyword_class_map

    def class_for_keyword(self, keyword: str) -> type[BaseParser] | None:
        return self.keyword_class_map.get(keyword)

    @property
    def enabled_platforms(self) -> list[str]:
        return [cls.platform.display_name for cls in self.enabled_classes]

    def instance(self, parser_cls: type[BaseParser]) -> BaseParser:
        """按需实例化 parser，并缓存结果"""
        parser = self._instances.get(parser_cls)
        if parser is None:
            parser = parser_cls()
            self._instances[parser_cls] = parser
        return parser

    def get_parser(self, keyword: str) -> BaseParser:
        """根据注册的关键字获取解析器实例（惰性加载）"""
        parser_cls = self.keyword_class_map.get(keyword)
        if parser_cls is None:
            raise KeyError(f"未找到关键字 {keyword!r} 对应的 parser")
        return self.instance(parser_cls)

    def get_parser_by_platform(self, platform: PlatformEnum) -> BaseParser | None:
        """按平台枚举获取解析器实例，未启用该平台时返回 ``None``

        仅在已启用（即已导入）的解析器中查找，禁用的平台不会被触碰
        """
        enabled = self.enabled_classes
        for cls, inst in self._instances.items():
            if cls.platform.name is platform and cls in enabled:
                return inst

        return next(
            (
                self.instance(cls)
                for cls in self.enabled_classes
                if cls.platform.name is platform
            ),
            None,
        )

    @property
    def instances(self) -> list[BaseParser]:
        return list(self._instances.values())

    async def run_startup(self) -> None:
        """实例化所有启用的解析器并逐个执行其启动钩子

        启动钩子相互独立，单个解析器失败不影响其它解析器
        """
        for parser_cls in self.enabled_classes:
            try:
                parser = self.instance(parser_cls)
                await parser.on_startup()
            except Exception:
                logger.exception(f"解析器 {parser_cls.__name__} 启动失败")

    async def aclose_all(self) -> None:
        """并发关闭所有已实例化的解析器，释放其持有的资源

        单个解析器关闭失败不影响其它解析器，但会记录日志
        """
        parsers = self.instances
        results = await asyncio.gather(
            *(parser.aclose() for parser in parsers),
            return_exceptions=True,
        )
        for parser, result in zip(parsers, results):
            if isinstance(result, BaseException):
                logger.error(f"解析器 {type(parser).__name__} 关闭失败: {result!r}")

    def reset(self) -> None:
        """清空注册表（主要供测试使用）"""
        self._enabled_classes = []
        self._instances = {}
        self._keyword_class_map = {}
        self._loaded = False


REGISTRY = ParserRegistry()

