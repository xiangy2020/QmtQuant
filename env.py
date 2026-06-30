"""
env.py - 项目平台环境配置模块

全项目唯一的 xtdata 入口。所有模块统一 from env import xtdata，
禁止直接 from xtquant import xtdata 或 from xqshare import xtdata。

接入方式：全平台统一通过 xqshare 连接 miniQMT。
  - Windows：.env 中 XQSHARE_REMOTE_HOST=127.0.0.1（连接本机 xqshare server）
  - Mac/Linux：.env 中 XQSHARE_REMOTE_HOST=<Windows 机器真实 IP>

平台常量（IS_MAC / IS_WINDOWS / IS_LINUX）仅供 OS 级操作使用（如打开文件、
路径分隔符等），与 xtdata 导入路径完全解耦。

使用方式：
    from env import xtdata
    from env import IS_MAC, IS_WINDOWS, IS_LINUX
"""

import os
import shutil
import logging
import platform as _platform

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 0. 缓存目录常量与一次性迁移（~/.qmtquant/）
# ------------------------------------------------------------------
_LEGACY_CACHE_DIR_NAME="~/.qmtquant/"
_CACHE_DIR_NAME = ".qmtquant"
_MIGRATION_DONE = False  # 模块级 flag，防止重复执行迁移


def _migrate_legacy_cache_dir() -> None:
    """
    一次性迁移历史缓存目录：~/.qmtquant/。

    规则：
      1. 若仅旧目录存在 → 使用 shutil.move 整体迁移到新目录，迁移后旧目录被自然删除。
      2. 若两者并存 → 仅打印一次警告（"检测到新旧缓存目录共存，使用新目录"），
         不迁移、不读取旧目录（避免覆盖用户在新目录上的最新数据）。
      3. 若仅新目录存在或都不存在 → 不做任何动作。

    迁移仅在模块导入时触发一次，由 _MIGRATION_DONE flag 防止重入。
    """
    global _MIGRATION_DONE
    if _MIGRATION_DONE:
        return
    _MIGRATION_DONE = True

    home = os.path.expanduser("~")
    legacy_dir = os.path.join(home, _LEGACY_CACHE_DIR_NAME)
    new_dir = os.path.join(home, _CACHE_DIR_NAME)

    legacy_exists = os.path.isdir(legacy_dir)
    new_exists = os.path.isdir(new_dir)

    if not legacy_exists:
        return  # 没有旧目录，无需处理

    if new_exists:
        logger.warning(
            "[env] 检测到新旧缓存目录共存：%s 与 %s 同时存在，将使用新目录，旧目录被忽略。"
            "如确认旧目录数据已不再需要，可手动删除 %s。",
            legacy_dir, new_dir, legacy_dir,
        )
        return

    try:
        logger.info("[env] 检测到旧缓存目录 %s，开始迁移到 %s ...", legacy_dir, new_dir)
        shutil.move(legacy_dir, new_dir)
        logger.info("[env] 缓存目录迁移完成：%s", new_dir)
    except Exception as _e:
        logger.error(
            "[env] 缓存目录迁移失败：%s\n"
            "请手动将 %s 的内容移动到 %s 后重启。",
            _e, legacy_dir, new_dir,
        )

# ------------------------------------------------------------------
# 1. 加载 .env 文件（查找项目根目录）
# ------------------------------------------------------------------

def _load_dotenv():
    """加载项目根目录的 .env 文件"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("[env] python-dotenv 未安装，跳过 .env 加载")
        return None

    # 从本文件所在目录向上查找 .env
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, ".env"),
        os.path.join(here, "..", ".env"),
    ]
    for p in candidates:
        p = os.path.normpath(p)
        if os.path.exists(p):
            load_dotenv(p, override=False)  # 系统环境变量优先
            logger.debug(f"[env] 已加载 .env：{p}")
            return p
    logger.debug("[env] 未找到 .env 文件，使用系统环境变量")
    return None


_ENV_FILE = _load_dotenv()

# ------------------------------------------------------------------
# 1.5 模块导入时一次性触发缓存目录迁移（~/.qmtquant/）
# ------------------------------------------------------------------
_migrate_legacy_cache_dir()

# ------------------------------------------------------------------
# 2. OS 级平台常量（仅供文件打开、路径等 OS 操作使用）
#    与 xtdata 导入路径完全解耦
# ------------------------------------------------------------------

_system = _platform.system()
IS_WINDOWS: bool = (_system == "Windows")
IS_MAC: bool     = (_system == "Darwin")
IS_LINUX: bool   = (_system == "Linux")

# IS_REMOTE 固定为 True：全平台统一走 xqshare，无本地直连路径
IS_REMOTE: bool  = True

# ------------------------------------------------------------------
# 3. xqshare 统一接入（全平台）
#    连接参数从 .env / 系统环境变量读取：
#      XQSHARE_REMOTE_HOST  - Windows 配 127.0.0.1，Mac/Linux 配真实 IP
#      XQSHARE_REMOTE_PORT  - 默认 18812
# ------------------------------------------------------------------

xtdata = None

try:
    import xqshare as _xqshare

    _host = os.environ.get("XQSHARE_REMOTE_HOST", "").strip()
    _port = int(os.environ.get("XQSHARE_REMOTE_PORT", "18812"))

    if not _host:
        logger.error(
            "[env] 未配置 XQSHARE_REMOTE_HOST。\n"
            "请在项目根目录的 .env 文件中添加：\n"
            "  XQSHARE_REMOTE_HOST=127.0.0.1        # Windows 本机\n"
            "  XQSHARE_REMOTE_HOST=192.168.x.x      # Mac/Linux 远程连接"
        )
    else:
        _xqshare.connect(host=_host, port=_port)
        xtdata = _xqshare.xtdata
        logger.info(f"[env] xqshare 已连接：{_host}:{_port}")

except ImportError:
    logger.error(
        "[env] 未找到 xqshare 模块。\n"
        "请安装 xqshare：pip install xqshare\n"
        "或参考文档：xqshare_src/README.md"
    )
except Exception as _e:
    logger.error(
        f"[env] xqshare 连接失败：{_e}\n"
        "请检查：\n"
        "  1. .env 中的 XQSHARE_REMOTE_HOST 配置是否正确\n"
        "  2. xqshare server 是否已在目标机器上启动\n"
        "  3. 网络是否可达（Windows 本机请确认 xqshare server 监听 0.0.0.0 或 127.0.0.1）"
    )

# ------------------------------------------------------------------
# 4. 平台相关路径工具
# ------------------------------------------------------------------

def get_cache_root() -> str:
    """获取本地数据缓存根目录（跨平台统一）"""
    return os.path.join(os.path.expanduser("~"), _CACHE_DIR_NAME, "cache")


def get_config_root() -> str:
    """获取配置文件根目录（跨平台统一）"""
    return os.path.join(os.path.expanduser("~"), _CACHE_DIR_NAME)


def open_file_in_os(path: str):
    """
    用系统默认程序打开文件（跨平台）。
    替代各处散落的 platform.system() 判断。
    """
    import subprocess
    if IS_WINDOWS:
        os.startfile(path)
    elif IS_MAC:
        subprocess.run(["open", path])
    else:  # Linux
        subprocess.run(["xdg-open", path])

# ------------------------------------------------------------------
# 5. 调试信息
# ------------------------------------------------------------------

def print_env_info():
    """打印当前平台环境信息（调试用）"""
    system_name = "Windows" if IS_WINDOWS else ("macOS" if IS_MAC else "Linux")
    print(f"[env] 运行平台：{system_name}")
    print(f"[env] IS_MAC={IS_MAC}, IS_WINDOWS={IS_WINDOWS}, IS_LINUX={IS_LINUX}")
    print(f"[env] IS_REMOTE={IS_REMOTE}（固定为 True，全平台统一走 xqshare）")
    print(f"[env] xtdata 已加载：{xtdata is not None}")
    print(f"[env] 缓存根目录：{get_cache_root()}")
    host = os.environ.get("XQSHARE_REMOTE_HOST", "<未配置>")
    port = os.environ.get("XQSHARE_REMOTE_PORT", "18812")
    print(f"[env] xqshare 连接目标：{host}:{port}")
    if _ENV_FILE:
        print(f"[env] .env 文件：{_ENV_FILE}")
    else:
        print(f"[env] ⚠ 未找到 .env 文件，使用系统环境变量")
