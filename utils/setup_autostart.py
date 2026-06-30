# -*- coding: utf-8 -*-
"""
setup_autostart.py — 注册/注销 qmt_watchdog 开机自启动
=======================================================
通过 Windows 任务计划程序（Task Scheduler）将 qmt_watchdog.py
注册为开机自动运行的后台任务，电脑重启后无需手动启动。

用法（在 Windows 端以管理员身份运行，激活虚拟环境后执行）：

  # 注册开机自启动
  python config/setup_autostart.py install

  # 查看当前注册状态
  python config/setup_autostart.py status

  # 注销开机自启动
  python config/setup_autostart.py uninstall

注意：此脚本仅支持在 Windows 上运行。
"""

import sys
import os
import subprocess

# ── Windows 平台检查 ──────────────────────────────────────────────
if sys.platform != "win32":
    print("此脚本仅支持在 Windows 上运行。")
    sys.exit(0)

# ── 常量 ──────────────────────────────────────────────────────────
TASK_NAME = "QMT_Watchdog"

# 脚本自身所在目录（config/），上一级为项目根目录
_config_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_config_DIR)
_WATCHDOG_SCRIPT = os.path.join(_config_DIR, "qmt_watchdog.py")
_PYTHON_EXE = sys.executable  # 使用当前激活虚拟环境的 Python


def _run(cmd: list, capture: bool = True) -> subprocess.CompletedProcess:
    """执行命令，返回 CompletedProcess"""
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def install():
    """注册任务计划程序，开机时自动以隐藏窗口运行 qmt_watchdog.py"""
    print(f"[setup_autostart] 正在注册任务：{TASK_NAME}")
    print(f"  Python  : {_PYTHON_EXE}")
    print(f"  脚本    : {_WATCHDOG_SCRIPT}")
    print(f"  工作目录: {_PROJECT_ROOT}")

    if not os.path.exists(_WATCHDOG_SCRIPT):
        print(f"❌ 找不到守护脚本：{_WATCHDOG_SCRIPT}")
        sys.exit(1)

    # 使用 schtasks 创建任务：
    #   /SC ONLOGON   — 用户登录时触发（比 ONSTART 更可靠，无需 SYSTEM 权限）
    #   /RL HIGHEST   — 以最高权限运行（避免 UAC 弹窗）
    #   /F            — 若任务已存在则强制覆盖
    #   /TR           — 运行的命令（pythonw.exe 不弹黑窗口）
    #
    # 注意：pythonw.exe 与 python.exe 同目录，专为无窗口后台运行设计
    pythonw = os.path.join(os.path.dirname(_PYTHON_EXE), "pythonw.exe")
    if not os.path.exists(pythonw):
        # 部分环境只有 python.exe，退而使用 python.exe（会有短暂黑窗口）
        pythonw = _PYTHON_EXE
        print("⚠️  未找到 pythonw.exe，将使用 python.exe（启动时会短暂出现命令行窗口）")

    # 命令行参数中路径含空格时需加引号
    tr = f'"{pythonw}" "{_WATCHDOG_SCRIPT}"'

    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", tr,
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/F",
    ]

    result = _run(cmd)
    if result.returncode == 0:
        print(f"✅ 任务注册成功：{TASK_NAME}")
        print("   电脑重启并登录后，qmt_watchdog 将自动在后台运行。")
        print(f"   可通过「任务计划程序」→「任务计划程序库」找到「{TASK_NAME}」查看详情。")
    else:
        print(f"❌ 注册失败（返回码 {result.returncode}）：")
        print(result.stderr or result.stdout)
        print("💡 提示：请尝试以管理员身份运行此脚本（右键 → 以管理员身份运行）")


def uninstall():
    """注销任务计划程序中的 qmt_watchdog 任务"""
    print(f"[setup_autostart] 正在注销任务：{TASK_NAME}")

    cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    result = _run(cmd)

    if result.returncode == 0:
        print(f"✅ 任务已注销：{TASK_NAME}")
    else:
        output = (result.stderr or result.stdout).strip()
        if "找不到" in output or "cannot find" in output.lower() or "does not exist" in output.lower():
            print(f"⚠️  任务不存在，无需注销：{TASK_NAME}")
        else:
            print(f"❌ 注销失败（返回码 {result.returncode}）：")
            print(output)


def status():
    """查询任务计划程序中 qmt_watchdog 的注册状态"""
    cmd = ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"]
    result = _run(cmd)

    if result.returncode == 0:
        print(f"✅ 任务已注册：{TASK_NAME}\n")
        # 只打印关键字段
        keywords = ("任务名称", "状态", "下次运行时间", "上次运行时间", "上次结果",
                    "Task Name", "Status", "Next Run Time", "Last Run Time", "Last Result",
                    "运行身份", "Run As User", "计划任务", "Scheduled Task")
        for line in result.stdout.splitlines():
            if any(kw in line for kw in keywords):
                print(" ", line.strip())
    else:
        output = (result.stderr or result.stdout).strip()
        if "找不到" in output or "cannot find" in output.lower() or "does not exist" in output.lower():
            print(f"⚠️  任务未注册：{TASK_NAME}")
            print("   运行 `python config/setup_autostart.py install` 可注册开机自启动。")
        else:
            print(f"❌ 查询失败（返回码 {result.returncode}）：")
            print(output)


def _print_usage():
    print("用法：python config/setup_autostart.py <命令>")
    print()
    print("命令：")
    print("  install    注册开机自启动（任务计划程序）")
    print("  uninstall  注销开机自启动")
    print("  status     查看当前注册状态")


# ── 脚本入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(0)

    command = sys.argv[1].lower()
    if command == "install":
        install()
    elif command == "uninstall":
        uninstall()
    elif command == "status":
        status()
    else:
        print(f"❌ 未知命令：{command}")
        print()
        _print_usage()
        sys.exit(1)
