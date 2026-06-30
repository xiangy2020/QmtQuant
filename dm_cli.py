# -*- coding: utf-8 -*-
"""
dm_cli.py — 数据管理模块 CLI 入口（转发文件，保持向后兼容）

实际实现已拆分至 dm_cli/ 目录下的各子模块：
    dm_cli/common.py         公共基础设施（日志、回调、工具函数）
    dm_cli/cmd_stats.py      stats 子命令
    dm_cli/cmd_validate.py   validate 子命令
    dm_cli/cmd_clear.py      clear 子命令
    dm_cli/cmd_sync.py       sync 子命令
    dm_cli/cmd_download.py  download / scan-gaps 子命令
    dm_cli/cmd_schedule.py   schedule 子命令
    dm_cli/main.py           build_parser() + main() 主入口
"""
from dm_cli.main import main  # noqa: F401

if __name__ == '__main__':
    main()
