"""
onboarding.py — 应用内新手引导

设计：
  - 不做「一次性大手册」，改为**用户打开对应功能时**弹出对应的分步引导
  - 每个引导有独立 key（api_key / mobile_remote / publish），显示过一次后不再自动弹
  - 用户取消勾选「不再自动显示」时，下次打开该功能还会再提示
  - 已看过的引导可从「帮助 → 📖 新手引导」手动重看，也可整体重置

状态保存在 config.yaml 的 onboarding.seen 列表里（随用户数据目录走）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from utils.config_loader import load_config, save_subsection
from .theme import PALETTE

SECTION = "onboarding"

# ---------------------------------------------------------------------------
# 引导文案
# ---------------------------------------------------------------------------

GUIDES: Dict[str, Dict[str, Any]] = {
    "api_key": {
        "title": "先配置 API Key（本软件的大脑）",
        "subtitle": "软件本身不含 AI 能力，所有识别 / 翻译 / 文案都靠你自己申请的 Key 完成。",
        "steps": [
            {
                "h": "① 为什么必须自己填",
                "body": (
                    "<p>Key 相当于你在这几个 AI 服务里的<b>个人钥匙</b>。软件不内置、也不共享别人的 Key，"
                    "所以新装好时这些输入框全是空的。</p>"
                    "<p>费用走你自己的账号，多数服务有免费额度，个人使用通常够用；"
                    "Key 只保存在本机配置文件里，不会上传到我们的服务器。</p>"
                ),
            },
            {
                "h": "② 必填：Gemini（字幕识别 / 翻译）",
                "body": (
                    "<ol>"
                    "<li>浏览器打开 <b>aistudio.google.com</b>，用 Google 账号登录</li>"
                    "<li>点左侧 <b>Get API key</b> → <b>Create API key</b>（已有则直接复制）</li>"
                    "<li>回到本软件：<b>工具 → 🔧 API 与 Cookie 管理 → 🔑 API Key & 提供商</b></li>"
                    "<li>把 Key 粘贴到 <b>Gemini</b> 那一行，点该行的编辑/保存</li>"
                    "</ol>"
                ),
            },
            {
                "h": "③ 可选：Groq / 自定义提供商",
                "body": (
                    "<ul>"
                    "<li><b>Groq</b>：console.groq.com 申请，文字处理更快，可以只作为备用</li>"
                    "<li><b>其他 OpenAI 兼容服务</b>（含本地 Ollama）：点「➕ 添加自定义提供商」，"
                    "填名称、接口地址、Key 即可</li>"
                    "</ul>"
                    "<p>不填也能用，只是没有备用模型。</p>"
                ),
            },
            {
                "h": "④ 搜索用：YouTube Data API Key",
                "body": (
                    "<p>在本页顶部「🌐 YouTube 数据 API」区域填写。</p>"
                    "<ol>"
                    "<li>打开 <b>console.cloud.google.com</b>，新建或选择项目</li>"
                    "<li>「API 和服务 → 库」搜索 <b>YouTube Data API v3</b> → 启用</li>"
                    "<li>「凭据 → 创建凭据 → API 密钥」→ 复制</li>"
                    "<li>粘贴到本软件并点「保存」</li>"
                    "</ol>"
                    "<p><b>不填也能用</b>：只是无法「按语言自动搜索」，手动粘贴视频链接照样能下载。</p>"
                ),
            },
            {
                "h": "⑤ 怎么确认配置成功",
                "body": (
                    "<p>点页面下方「🔌 扫描全部已启用」，出现绿色 ✔ 就表示 Key 可用。</p>"
                    "<ul>"
                    "<li><b>401 / 403</b>：Key 填错、粘贴多了空格，或服务未开通</li>"
                    "<li><b>超时</b>：电脑网络/代理问题，先确认浏览器能打开对应网站</li>"
                    "</ul>"
                    "<p>填错了随时回来改，改完重新扫描即可。</p>"
                    "<p>TikTok / 抖音需要的 Cookie 也在同一个对话框，"
                    "点顶部 <b>🍪 Cookie</b> 标签填写。</p>"
                ),
            },
        ],
    },
    "mobile_remote": {
        "title": "手机远程遥控电脑",
        "subtitle": "不用装 App —— 手机浏览器扫码即可操作电脑上的任务。",
        "steps": [
            {
                "h": "① 它是什么",
                "body": (
                    "<p>手机相当于<b>遥控器</b>，真正的下载、识别、翻译、发布全部在电脑上跑。</p>"
                    "<p>所以你可以在外面用手机发起任务，回家直接看成品。</p>"
                ),
            },
            {
                "h": "② 开启步骤",
                "body": (
                    "<ol>"
                    "<li>保持本软件（GUI）开着</li>"
                    "<li>点菜单 <b>工具 → 📱 启动远程联动</b></li>"
                    "<li>弹出二维码后，用手机相机 / 微信扫一扫</li>"
                    "<li>手机上会打开一个网页，就是全部功能面板</li>"
                    "</ol>"
                ),
            },
            {
                "h": "③ 两种连接模式（最常见的问题来源）",
                "body": (
                    "<ul>"
                    "<li><b>🌐 公网模式</b>：手机用 4G/5G 或任意 WiFi 都能连（推荐）</li>"
                    "<li><b>📶 局域网模式</b>：手机必须和电脑连同一个 WiFi，换成流量就打不开</li>"
                    "</ul>"
                    "<p>二维码上方会标明当前是哪种模式。打不开时先看这一条。</p>"
                ),
            },
            {
                "h": "④ 正常运转的前提",
                "body": (
                    "<ul>"
                    "<li><b>电脑不能关机，也不能睡眠</b>（建议电源设置改成「从不睡眠」）</li>"
                    "<li><b>GUI 必须保持运行</b>，最小化可以，关掉就不行了</li>"
                    "<li>电脑要联网；用公网模式时手机也要联网</li>"
                    "<li>同一台电脑只开一个 GUI（重复开启会抢端口）</li>"
                    "<li>手机网页可以随时关，任务在电脑上继续跑，重开网页看「日志」即可</li>"
                    "</ul>"
                ),
            },
            {
                "h": "⑤ 手机上能做什么",
                "body": (
                    "<p>发起下载/识别/翻译/发布、查看进度和日志、选成品入发布队列。</p>"
                    "<p>不能做的：编辑本地文件、改高级参数 —— 这些还是回电脑上操作。</p>"
                ),
            },
            {
                "h": "⑥ 连不上怎么办",
                "body": (
                    "<ol>"
                    "<li>看二维码是「公网」还是「局域网」，模式和手机网络不匹配最常见</li>"
                    "<li>确认电脑没有睡眠、GUI 没被关掉</li>"
                    "<li>公司/校园网可能封端口，手机切到流量再试</li>"
                    "<li>还不行：电脑上点「🔄 强制重启」后重新出二维码</li>"
                    "</ol>"
                ),
            },
        ],
    },
    "publish": {
        "title": "自动发布：先把账号导进来",
        "subtitle": "账号 Cookie 存在本机；发布由后台队列按节奏执行。",
        "steps": [
            {
                "h": "① 它怎么工作",
                "body": (
                    "<p>流程：<b>成品视频 → 候选池 → 选账号入队 → 后台自动上传 → 平台发布成功</b></p>"
                    "<p>所以发布页里既能选「最近完成」的成品，也能翻更早的。</p>"
                ),
            },
            {
                "h": "② 导入账号（关键一步）",
                "body": (
                    "<ol>"
                    "<li>在 <b>⑤ 视频发布</b> 页选平台标签（B站 / 抖音 / 小红书 / 快手）</li>"
                    "<li>先在<b>浏览器里登录</b>好这个平台的账号</li>"
                    "<li>点 <b>➕ 添加账号</b> → <b>🌐 从浏览器实时拉取 Cookie</b>（推荐）</li>"
                    "<li>也可以手动粘贴 Cookie 字符串（Netscape / header / JSON 都支持）</li>"
                    "<li>点 <b>🔍 探测有效性</b>，显示有效才算导入成功</li>"
                    "</ol>"
                    "<p>Cookie 相当于账号登录凭证，<b>只保存在本机</b>，不会上传。</p>"
                ),
            },
            {
                "h": "③ 发布一条",
                "body": (
                    "<ol>"
                    "<li>左侧选成品（默认最近 3 天，可切「所有视频」）</li>"
                    "<li>右侧选账号</li>"
                    "<li>点「入队」或「🚀 立即发布」</li>"
                    "<li>在发布队列里看进度：排队 → 上传 → 成功/失败</li>"
                    "</ol>"
                ),
            },
            {
                "h": "④ 为什么「变慢」了（这是保护，不是故障）",
                "body": (
                    "<p>默认节奏：<b>每条之间随机 10~30 分钟</b>，<b>每天最多 5 条</b>。</p>"
                    "<p>超过上限会显示「已跳过」，而不是硬发 —— 这是为了降低被平台风控的概率。</p>"
                    "<p>确实需要调整，可在 config.yaml 的 <b>publish</b> 段修改冷却时间和每日上限。</p>"
                ),
            },
            {
                "h": "⑤ 风险提示（务必看完）",
                "body": (
                    "<ul>"
                    "<li>第三方自动发布<b>不完全符合各平台条款</b>，可能被限流甚至封号，风险自担</li>"
                    "<li><b>小红书风控最严</b>，强烈建议手动发布为主</li>"
                    "<li>Cookie 等同于账号密码：<b>不要截图发到群里、不要发给别人</b></li>"
                    "<li>建议先用小号/不重要账号试，不要一上来就批量发</li>"
                    "<li>官方 API 通道（B站/抖音）需要企业资质或能力申请，个人用户实际走 Cookie</li>"
                    "</ul>"
                ),
            },
        ],
    },
    "tiktok_cookie": {
        "title": "TikTok / 抖音 需要你浏览器里的 Cookie",
        "subtitle": "这两个平台已不允许匿名解析，必须提供一份 cookie 文件才能下载。",
        "steps": [
            {
                "h": "① 为什么必须自己提供",
                "body": (
                    "<p>抖音和 TikTok 的网页接口会校验 <b>s_v_web_id、ttwid、msToken</b> 等登录态标识。"
                    "没有这些 cookie 时，yt-dlp 会直接报 "
                    "<b>Fresh cookies (not necessarily logged in) are needed</b> 或 "
                    "<b>Your IP address is blocked</b>。</p>"
                    "<p>软件<b>不内置也不共享</b>任何人的 cookie；文件只放在你本机，不会上传。</p>"
                ),
            },
            {
                "h": "② 怎么导出（3 分钟）",
                "body": (
                    "<ol>"
                    "<li>浏览器装扩展 <b>Cookie-Editor</b> 或 <b>Get cookies.txt LOCALLY</b></li>"
                    "<li>登录 <b>tiktok.com</b>（或 douyin.com），随便刷一下首页，让 cookie 变新</li>"
                    "<li>在该网站上点扩展图标 → <b>Export</b> → 得到 Netscape 格式的 cookies 文件</li>"
                    "<li>两个平台各导一次，把内容合并成一个 .txt 也可以用</li>"
                    "</ol>"
                ),
            },
            {
                "h": "③ 放到哪里（软件自动读取）",
                "body": (
                    "<p>放到数据目录下的 <b>data\\browser_cookies.txt</b>，不用改任何配置。</p>"
                    "<p>文件名必须是 <b>browser_cookies.txt</b>；路径随「用户数据目录」走，"
                    "点下方按钮可以直接打开所在文件夹。</p>"
                    "<p>也可以用下载页的测试脚本临时指定：<br>"
                    "<code>--cookies 路径\\cookies.txt</code></p>"
                ),
            },
            {
                "h": "④ 维护：多久更新一次",
                "body": (
                    "<ul>"
                    "<li>一般能撑 <b>7~30 天</b>，平台随时可能提前失效</li>"
                    "<li>出现下列情况就是该更新了：解析失败、提示 Fresh cookies、突然要求人机验证、"
                    "或某条视频一直下载不到</li>"
                    "<li>更新方式：重新导出一次，<b>覆盖</b>原来的 browser_cookies.txt 即可</li>"
                    "<li>导出后别马上清缓存/退出登录，否则文件会立刻失效</li>"
                    "<li>换电脑、重装浏览器后需要重新导出</li>"
                    "</ul>"
                ),
            },
            {
                "h": "⑤ 风险提示（务必看完）",
                "body": (
                    "<ul>"
                    "<li>Cookie 等同于<b>账号登录凭证</b>，拿到的人可以直接操作你的账号："
                    "<b>不要发给别人、不要截图、不要提交到 Git</b>（该文件已在本项目 .gitignore 里）</li>"
                    "<li>用已登录账号高频抓取可能触发平台风控，建议用<b>专用小号</b>，不要用主号</li>"
                    "<li>怀疑泄露时：立刻在该平台「退出所有设备」并修改密码，再重新导出</li>"
                    "<li>下载他人视频并二次发布存在<b>版权风险</b>，请自行判断使用场景</li>"
                    "</ul>"
                ),
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# 已看状态读写
# ---------------------------------------------------------------------------

def _seen_list() -> List[str]:
    try:
        raw = (load_config().get(SECTION) or {}).get("seen", [])
        return [str(x) for x in raw] if isinstance(raw, list) else []
    except Exception:
        return []


def has_seen(key: str) -> bool:
    """该引导是否已经展示过（不再自动弹）"""
    return key in _seen_list()


def mark_seen(key: str) -> None:
    """记录已看过（幂等）"""
    seen = _seen_list()
    if key in seen:
        return
    seen.append(key)
    try:
        save_subsection(SECTION, {"seen": seen})
    except Exception:
        pass  # 配置写失败不影响主流程


def reset_onboarding() -> None:
    """重置全部引导（下次打开功能时重新弹出）"""
    try:
        save_subsection(SECTION, {"seen": []})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 引导对话框
# ---------------------------------------------------------------------------

class GuideDialog(QDialog):
    """分步引导对话框：上一步 / 下一步 / 跳过，可勾选「不再自动显示」。"""

    def __init__(
        self,
        guide: Dict[str, Any],
        parent: Optional[QWidget] = None,
        actions: Optional[List[Tuple[str, Callable[[], None]]]] = None,
    ) -> None:
        super().__init__(parent)
        self._steps: List[Dict[str, str]] = list(guide.get("steps") or [])
        self._idx = 0
        self.mark_seen = True          # 关闭时是否记录已看
        self.chosen_action: Optional[Callable[[], None]] = None

        self.setWindowTitle("新手引导")
        self.setMinimumWidth(600)
        self.setModal(True)
        self._build(guide, actions or [])
        self._render()

    # ---- UI ----
    def _build(self, guide: Dict[str, Any], actions: List[Tuple[str, Callable[[], None]]]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(8)

        title = QLabel(guide.get("title", "新手引导"))
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        sub = QLabel(guide.get("subtitle", ""))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {PALETTE['text_muted']};")
        root.addWidget(sub)

        self._counter = QLabel("")
        self._counter.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 12px;")
        root.addWidget(self._counter)

        self._h = QLabel("")
        self._h.setStyleSheet("font-size: 14px; font-weight: 600; padding-top: 4px;")
        self._h.setWordWrap(True)
        root.addWidget(self._h)

        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._body.setMinimumHeight(190)
        self._body.setStyleSheet(f"color: {PALETTE['text_primary']};")
        root.addWidget(self._body, 1)

        self._chk = QCheckBox("不再自动显示此引导（可从「帮助 → 📖 新手引导」重看）")
        self._chk.setChecked(True)
        root.addWidget(self._chk)

        root.addStretch(0)

        btn_row = QHBoxLayout()
        for label, cb in actions:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, f=cb: self._run_action(f))
            btn_row.addWidget(btn)
        btn_row.addStretch(1)

        self._btn_prev = QPushButton("上一步")
        self._btn_prev.clicked.connect(self._prev)
        self._btn_skip = QPushButton("跳过")
        self._btn_skip.clicked.connect(self._skip)
        self._btn_next = QPushButton("下一步")
        self._btn_next.setDefault(True)
        self._btn_next.clicked.connect(self._next)
        for b in (self._btn_prev, self._btn_skip, self._btn_next):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

    # ---- 行为 ----
    def _render(self) -> None:
        step = self._steps[self._idx]
        self._h.setText(step.get("h", ""))
        self._body.setText(step.get("body", ""))
        self._counter.setText(f"第 {self._idx + 1} / {len(self._steps)} 步")
        self._btn_prev.setEnabled(self._idx > 0)
        self._btn_next.setText("开始使用" if self._idx >= len(self._steps) - 1 else "下一步")

    def _next(self) -> None:
        if self._idx >= len(self._steps) - 1:
            self.accept()
            return
        self._idx += 1
        self._render()

    def _prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1
            self._render()

    def _skip(self) -> None:
        self.mark_seen = self._chk.isChecked()
        self.reject()

    def _run_action(self, cb: Callable[[], None]) -> None:
        self.chosen_action = cb
        self.accept()

    def accept(self) -> None:  # noqa: D401 — Qt 覆写
        self.mark_seen = self._chk.isChecked()
        super().accept()


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

def show_guide(
    parent: Optional[QWidget],
    key: str,
    actions: Optional[List[Tuple[str, Callable[[], None]]]] = None,
) -> bool:
    """强制展示某个引导（用于「帮助 → 新手引导」手动重看）"""
    guide = GUIDES.get(key)
    if not guide:
        return False
    dlg = GuideDialog(guide, parent=parent, actions=actions)
    dlg.exec()
    if dlg.chosen_action:
        try:
            dlg.chosen_action()
        except Exception:
            pass
    return True


def maybe_show_guide(
    parent: Optional[QWidget],
    key: str,
    actions: Optional[List[Tuple[str, Callable[[], None]]]] = None,
) -> bool:
    """首次打开某功能时自动展示；已看过则静默跳过"""
    if has_seen(key):
        return False
    return show_guide(parent, key, actions=actions)
