#!/usr/bin/env bash
# =============================================================================
# QmtQuant Linux 一键部署脚本
# 用途：在全新 Linux 服务器上完成环境初始化
# 项目目录：/data2/qmtquant
# =============================================================================

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
section() { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}"; }

# ── 常量 ──────────────────────────────────────────────────────────────────────
PROJECT_DIR="/data2/qmtquant"
VENV_DIR="${PROJECT_DIR}/venv"
PYTHON_BIN=""
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=13

# ── --help ────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
用法：bash deploy/setup.sh [选项]

QmtQuant Linux 一键部署脚本。
在全新 Linux 服务器上完成以下初始化步骤：
  1. 检查 Python 3.13 是否已安装
  2. 创建项目目录 ${PROJECT_DIR}
  3. 创建 Python 虚拟环境 ${VENV_DIR}
  4. 安装 requirements.txt 中的全部依赖
  5. 打印关键依赖版本摘要
  6. 提示 systemd 服务安装命令

选项：
  --help    显示此帮助信息并退出

前置条件：
  - Python 3.13 已安装（推荐通过 deadsnakes PPA 安装）
  - 项目代码已克隆到 ${PROJECT_DIR}
  - 已复制并填写 .env 文件（参考 deploy/env.linux.example）

示例：
  # 在项目根目录执行
  bash deploy/setup.sh

安装 Python 3.13（Ubuntu/Debian）：
  sudo add-apt-repository ppa:deadsnakes/ppa
  sudo apt update
  sudo apt install python3.13 python3.13-venv python3.13-dev

安装 Python 3.13（CentOS/RHEL/TencentOS，源码编译）：
  sudo yum groupinstall -y "Development Tools"
  sudo yum install -y openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel xz-devel wget
  cd /tmp && wget https://www.python.org/ftp/python/3.13.0/Python-3.13.0.tgz
  tar -xzf Python-3.13.0.tgz && cd Python-3.13.0
  ./configure --enable-optimizations --with-ensurepip=install
  make -j\$(nproc) && sudo make altinstall
EOF
}

if [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

# ── 步骤 1：检查 Python 3.13 ──────────────────────────────────────────────────
section "步骤 1：检查 Python 3.13"

find_python313() {
    for candidate in python3.13 python3 python; do
        if command -v "$candidate" &>/dev/null; then
            local ver
            ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [[ "$major" == "$REQUIRED_PYTHON_MAJOR" && "$minor" == "$REQUIRED_PYTHON_MINOR" ]]; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

if PYTHON_BIN=$(find_python313); then
    PY_VER=$("$PYTHON_BIN" --version 2>&1)
    info "找到 Python 3.13：${PYTHON_BIN}（${PY_VER}）"
else
    error "未找到 Python 3.13，请先安装后再运行本脚本。"
    echo ""
    echo "  Ubuntu/Debian 安装方式："
    echo "    sudo add-apt-repository ppa:deadsnakes/ppa"
    echo "    sudo apt update"
    echo "    sudo apt install python3.13 python3.13-venv python3.13-dev"
    echo ""
    echo "  CentOS/RHEL/TencentOS 安装方式（源码编译）："
    echo "    sudo yum groupinstall -y 'Development Tools'"
    echo "    sudo yum install -y openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel xz-devel wget"
    echo "    cd /tmp && wget https://www.python.org/ftp/python/3.13.0/Python-3.13.0.tgz"
    echo "    tar -xzf Python-3.13.0.tgz && cd Python-3.13.0"
    echo "    ./configure --enable-optimizations --with-ensurepip=install"
    echo "    make -j\$(nproc) && sudo make altinstall"
    echo ""
    exit 1
fi

# ── 步骤 2：创建项目目录 ──────────────────────────────────────────────────────
section "步骤 2：创建项目目录"

if [[ ! -d "$PROJECT_DIR" ]]; then
    info "创建目录：${PROJECT_DIR}"
    mkdir -p "$PROJECT_DIR"
else
    info "目录已存在，跳过：${PROJECT_DIR}"
fi

# 确认脚本在项目根目录下运行
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "$REPO_ROOT" != "$PROJECT_DIR" ]]; then
    warn "当前项目路径（${REPO_ROOT}）与目标路径（${PROJECT_DIR}）不一致。"
    warn "请确保项目已克隆到 ${PROJECT_DIR}，或在正确目录下运行本脚本。"
fi

# ── 步骤 3：创建虚拟环境（幂等）──────────────────────────────────────────────
section "步骤 3：创建 Python 虚拟环境"

if [[ -d "$VENV_DIR" ]]; then
    info "虚拟环境已存在，跳过创建：${VENV_DIR}"
else
    info "创建虚拟环境：${VENV_DIR}"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    info "虚拟环境创建完成"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"

# ── 步骤 4：安装依赖 ──────────────────────────────────────────────────────────
section "步骤 4：安装依赖"

REQUIREMENTS="${REPO_ROOT}/requirements.txt"
if [[ ! -f "$REQUIREMENTS" ]]; then
    error "未找到 requirements.txt：${REQUIREMENTS}"
    exit 1
fi

info "升级 pip..."
"$VENV_PYTHON" -m pip install --upgrade pip -q

info "安装依赖（来自 ${REQUIREMENTS}）..."
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS" -q
info "依赖安装完成"

# ── 步骤 5：打印版本摘要 ──────────────────────────────────────────────────────
section "步骤 5：关键依赖版本摘要"

print_pkg_version() {
    local pkg="$1"
    local ver
    ver=$("$VENV_PYTHON" -c "import importlib.metadata; print(importlib.metadata.version('$pkg'))" 2>/dev/null || echo "未安装")
    printf "  %-20s %s\n" "$pkg" "$ver"
}

echo ""
printf "  %-20s %s\n" "Python" "$("$VENV_PYTHON" --version 2>&1 | awk '{print $2}')"
print_pkg_version "fastapi"
print_pkg_version "uvicorn"
print_pkg_version "pandas"
print_pkg_version "pyarrow"
print_pkg_version "python-dotenv"
echo ""

# ── 步骤 6：提示 systemd 服务安装 ────────────────────────────────────────────
section "步骤 6：systemd 服务安装（需 sudo）"

DEPLOY_DIR="${REPO_ROOT}/deploy"

echo ""
info "请手动执行以下命令安装 systemd 服务（需要 sudo 权限）："
echo ""
echo "  # 复制服务文件"
echo "  sudo cp ${DEPLOY_DIR}/qmtquant-api.service  /etc/systemd/system/"
echo "  sudo cp ${DEPLOY_DIR}/qmtquant-sync.service /etc/systemd/system/"
echo "  sudo cp ${DEPLOY_DIR}/qmtquant-sync.timer   /etc/systemd/system/"
echo ""
echo "  # 重新加载 systemd 配置"
echo "  sudo systemctl daemon-reload"
echo ""
echo "  # 启动并设置开机自启 data-api 服务"
echo "  sudo systemctl enable --now qmtquant-api"
echo ""
echo "  # 启动并设置开机自启数据同步定时器"
echo "  sudo systemctl enable --now qmtquant-sync.timer"
echo ""

# ── 完成 ──────────────────────────────────────────────────────────────────────
section "部署完成"

echo ""
info "✅ 环境初始化完成！"
echo ""
echo "  下一步："
echo "  1. 复制并填写配置文件："
echo "     cp ${DEPLOY_DIR}/env.linux.example ${PROJECT_DIR}/.env"
echo "     vim ${PROJECT_DIR}/.env   # 填写 XQSHARE_REMOTE_HOST 等配置"
echo ""
echo "  2. 安装 systemd 服务（见上方命令）"
echo ""
echo "  3. 验证服务是否正常："
echo "     curl http://localhost:8765/health"
echo ""
echo "  详细部署文档：${DEPLOY_DIR}/README.md"
echo ""
