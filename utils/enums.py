r"""
全局枚举定义模块
所有状态、语种、分类、日志标签等统一在此定义，禁止硬编码

状态流转规则（TaskStatus）：
    PENDING(1) -> CRAWLING(2) -> DOWNLOADED(3) -> TRANSLATING(4) -> COMPLETED(5)
                           \         \         \
                            \-> FAILED(6)       \-> FAILED(6)
                                     \                 /
                                      \--> DEAD_LETTER(7) （超过max_retry次失败后）
    终态：COMPLETED(5)、DEAD_LETTER(7) — 不可回退、不可再次流转
"""

from enum import IntEnum, StrEnum
from typing import Optional, Type, TypeVar

E = TypeVar("E", bound="BaseEnumMixin")


class BaseEnumMixin:
    """枚举通用工具方法混入类"""

    @classmethod
    def is_valid(cls: Type[E], value: object) -> bool:
        """校验值是否为合法枚举值

        Args:
            value: 待校验的值

        Returns:
            True表示合法，False表示非法
        """
        try:
            cls(value)  # type: ignore[call-arg]
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def from_code(cls: Type[E], code: object, default: Optional[E] = None) -> Optional[E]:
        """从编码值安全转换为枚举实例，非法值返回默认值

        Args:
            code: 原始编码值
            default: 转换失败时的默认返回值

        Returns:
            枚举实例或默认值
        """
        try:
            return cls(code)  # type: ignore[call-arg]
        except (ValueError, TypeError):
            return default

    @classmethod
    def from_int(cls: Type[E], value: int, default: Optional[E] = None) -> Optional[E]:
        """从整数转换为枚举实例（IntEnum专用别名）

        Args:
            value: 整数值
            default: 转换失败时的默认返回值

        Returns:
            枚举实例或默认值
        """
        return cls.from_code(value, default)  # type: ignore[arg-type]

    @classmethod
    def from_db(cls: Type[E], db_value: object, default: Optional[E] = None) -> Optional[E]:
        """从数据库读取值转换为枚举实例

        Args:
            db_value: 数据库存储值
            default: 转换失败时的默认返回值

        Returns:
            枚举实例或默认值
        """
        return cls.from_code(db_value, default)

    @property
    def display_name(self) -> str:
        """中文展示名称，用于前端/日志可读性展示"""
        name_map = _DISPLAY_NAMES.get(type(self), {})
        return name_map.get(self, self.name)

    @property
    def is_final(self) -> bool:
        """是否为终态（终态不可回退、不可再次流转）"""
        final_set = _FINAL_STATUS_MAP.get(type(self), set())
        return self in final_set


# ---------------------------------------------------------
# 状态流转定义
# ---------------------------------------------------------

# 各枚举的中文展示名映射
_DISPLAY_NAMES: dict[type, dict[object, str]] = {}

# 各枚举的终态集合
_FINAL_STATUS_MAP: dict[type, set[object]] = {}


class TaskStatus(BaseEnumMixin, IntEnum):
    r"""
    任务全局状态机（数字存入数据库，代码使用枚举）

    合法状态流转：
        PENDING(1) 待抓取
            -> CRAWLING(2) 采集中
        CRAWLING(2) 采集中
            -> DOWNLOADED(3) 下载完成
            -> FAILED(6) 采集失败
        DOWNLOADED(3) 下载完成，等待翻译
            -> TRANSLATING(4) 字幕翻译中
            -> FAILED(6) 创建翻译任务失败
        TRANSLATING(4) 字幕翻译中
            -> COMPLETED(5) 全部流程完成
            -> FAILED(6) 翻译失败
        FAILED(6) 单次执行失败，可重试
            -> TRANSLATING(4) 重试（retry_count < max_retry）
            -> DEAD_LETTER(7) 超过重试次数进入死信
        COMPLETED(5)、DEAD_LETTER(7) 为终态，不可回退
    """
    PENDING = 1          # 待抓取
    CRAWLING = 2         # 采集中
    DOWNLOADED = 3       # 下载完成，等待翻译
    TRANSLATING = 4      # 字幕翻译中
    COMPLETED = 5        # 全部流程完成
    FAILED = 6           # 单次执行失败，可重试
    DEAD_LETTER = 7      # 多次重试失败，死信任务

    def can_transition_to(self, target: "TaskStatus") -> bool:
        """判断当前状态是否允许流转到目标状态

        Args:
            target: 目标状态

        Returns:
            True表示允许流转
        """
        if self.is_final:
            return False
        allowed = _STATUS_TRANSITIONS.get(self, set())
        return target in allowed


# 状态流转允许关系表
_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.CRAWLING, TaskStatus.FAILED},
    TaskStatus.CRAWLING: {TaskStatus.DOWNLOADED, TaskStatus.FAILED},
    TaskStatus.DOWNLOADED: {TaskStatus.TRANSLATING, TaskStatus.FAILED},
    TaskStatus.TRANSLATING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.FAILED: {TaskStatus.TRANSLATING, TaskStatus.DEAD_LETTER},
}

# TaskStatus 终态集合
_FINAL_STATUS_MAP[TaskStatus] = {TaskStatus.COMPLETED, TaskStatus.DEAD_LETTER}

# TaskStatus 中文展示名
_DISPLAY_NAMES[TaskStatus] = {
    TaskStatus.PENDING: "待抓取",
    TaskStatus.CRAWLING: "采集中",
    TaskStatus.DOWNLOADED: "下载完成",
    TaskStatus.TRANSLATING: "翻译中",
    TaskStatus.COMPLETED: "已完成",
    TaskStatus.FAILED: "失败",
    TaskStatus.DEAD_LETTER: "死信",
}


class LanguageType(BaseEnumMixin, StrEnum):
    """
    视频源语种枚举
    与 video_info.lang 字段一一对应
    支持多语种识别，爬虫可通过白名单过滤
    """
    # 主要支持的语言
    GERMAN = "de"
    FRENCH = "fr"
    SPANISH = "es"
    ENGLISH = "en"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    RUSSIAN = "ru"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    ARABIC = "ar"
    HINDI = "hi"
    # 其他常见语言
    DUTCH = "nl"
    SWEDISH = "sv"
    NORWEGIAN = "no"
    DANISH = "da"
    FINNISH = "fi"
    POLISH = "pl"
    CZECH = "cs"
    HUNGARIAN = "hu"
    ROMANIAN = "ro"
    GREEK = "el"
    TURKISH = "tr"
    VIETNAMESE = "vi"
    THAI = "th"
    INDONESIAN = "id"
    MALAY = "ms"
    TAGALOG = "tl"


_DISPLAY_NAMES[LanguageType] = {
    LanguageType.GERMAN: "德语",
    LanguageType.FRENCH: "法语",
    LanguageType.SPANISH: "西班牙语",
    LanguageType.ENGLISH: "英语",
    LanguageType.CHINESE: "中文",
    LanguageType.JAPANESE: "日语",
    LanguageType.KOREAN: "韩语",
    LanguageType.RUSSIAN: "俄语",
    LanguageType.ITALIAN: "意大利语",
    LanguageType.PORTUGUESE: "葡萄牙语",
    LanguageType.ARABIC: "阿拉伯语",
    LanguageType.HINDI: "印地语",
    LanguageType.DUTCH: "荷兰语",
    LanguageType.SWEDISH: "瑞典语",
    LanguageType.NORWEGIAN: "挪威语",
    LanguageType.DANISH: "丹麦语",
    LanguageType.FINNISH: "芬兰语",
    LanguageType.POLISH: "波兰语",
    LanguageType.CZECH: "捷克语",
    LanguageType.HUNGARIAN: "匈牙利语",
    LanguageType.ROMANIAN: "罗马尼亚语",
    LanguageType.GREEK: "希腊语",
    LanguageType.TURKISH: "土耳其语",
    LanguageType.VIETNAMESE: "越南语",
    LanguageType.THAI: "泰语",
    LanguageType.INDONESIAN: "印尼语",
    LanguageType.MALAY: "马来语",
    LanguageType.TAGALOG: "他加禄语",
}


class VideoCategory(BaseEnumMixin, StrEnum):
    """
    视频题材分类枚举
    与 video_info.category 字段一一对应
    """
    SCIENCE = "science"
    DAILY = "daily"
    ENTERTAINMENT = "entertainment"
    NEWS = "news"


_DISPLAY_NAMES[VideoCategory] = {
    VideoCategory.SCIENCE: "科普",
    VideoCategory.DAILY: "日常",
    VideoCategory.ENTERTAINMENT: "娱乐",
    VideoCategory.NEWS: "新闻",
}


class LogTag(BaseEnumMixin, StrEnum):
    """日志分类标识，用于分文件输出日志"""
    CRAWLER = "crawler"
    DOWNLOAD = "download"
    TRANSLATE = "translate"
    ERROR = "error"


_DISPLAY_NAMES[LogTag] = {
    LogTag.CRAWLER: "爬虫",
    LogTag.DOWNLOAD: "下载",
    LogTag.TRANSLATE: "翻译",
    LogTag.ERROR: "错误",
}


class SubtitleMode(BaseEnumMixin, StrEnum):
    """字幕翻译对接模式"""
    API = "api"
    FOLDER = "folder"


_DISPLAY_NAMES[SubtitleMode] = {
    SubtitleMode.API: "API模式",
    SubtitleMode.FOLDER: "文件夹模式",
}


class TaskPriority(BaseEnumMixin, IntEnum):
    """任务优先级枚举"""
    NORMAL = 0
    HIGH = 1


_DISPLAY_NAMES[TaskPriority] = {
    TaskPriority.NORMAL: "普通",
    TaskPriority.HIGH: "高优先级",
}

_FINAL_STATUS_MAP[TaskPriority] = set()
