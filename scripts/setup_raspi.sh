#!/bin/bash
#
# Raspberry Pi ライブラリ最小セットアップスクリプト
#
# BLE 受信ライブラリ（raspi_receiver/lib）利用に必要な最小構成のみを行う。
# LCD や SPI/GPIO 依存は含めない。
#
# 使用方法:
#   chmod +x scripts/setup_raspi.sh
#   sudo ./scripts/setup_raspi.sh
#   sudo ./scripts/setup_raspi.sh --venv
#   sudo ./scripts/setup_raspi.sh --venv /path/to/venv
#
# LCD サンプルを使う場合:
#   sudo ./sample/scripts/setup_raspi_sample.sh [--venv [path]]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

USE_VENV=false
VENV_DIR="$PROJECT_ROOT/.venv"

while [ $# -gt 0 ]; do
    case "$1" in
        --venv)
            USE_VENV=true
            if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
                VENV_DIR="$2"
                shift
            fi
            shift
            ;;
        *)
            echo "不明なオプション: $1"
            echo "使用方法: sudo ./scripts/setup_raspi.sh [--venv [パス]]"
            exit 1
            ;;
    esac
done

if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./scripts/setup_raspi.sh"
    exit 1
fi

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi Library Setup"
if $USE_VENV; then
    echo "モード: venv ($VENV_DIR)"
else
    echo "モード: システムワイド"
fi
echo "=========================================="

APT_CONF="/etc/apt/apt.conf.d/99force-ipv4"
if [ ! -f "$APT_CONF" ]; then
    echo 'Acquire::ForceIPv4 "true";' > "$APT_CONF"
    echo "  IPv4 強制設定を追加: $APT_CONF"
fi

echo ""
echo "[1/4] 必須システムパッケージをインストール..."
apt update
apt install -y \
    bluez \
    python3-pip \
    python3-dev \
    libcap2-bin

if $USE_VENV; then
    apt install -y python3-venv
fi

echo "  完了"

echo ""
echo "[2/4] bless をインストール..."
ACTUAL_USER="${SUDO_USER:-$USER}"

if $USE_VENV; then
    SYSTEM_PYTHON="/usr/bin/python3"
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install "bless>=0.3.0"

    if [ "$ACTUAL_USER" != "root" ]; then
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$VENV_DIR"
    fi
    PYTHON_PATH="$(readlink -f "$VENV_DIR/bin/python3")"
else
    PIP_FLAGS=""
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PIP_FLAGS="--break-system-packages"
    fi
    pip3 install $PIP_FLAGS "bless>=0.3.0"
    PYTHON_PATH="$(readlink -f "$(which python3)")"
fi

echo "  完了"

echo ""
echo "[3/4] Bluetooth サービス設定..."
systemctl enable bluetooth
systemctl start bluetooth || true

if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up || true
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
fi

echo ""
echo "[4/4] 非 root 実行の権限設定..."
if [ "$ACTUAL_USER" != "root" ]; then
    usermod -aG bluetooth "$ACTUAL_USER" 2>/dev/null && echo "  bluetooth グループに追加" || true

    if [ -n "$PYTHON_PATH" ]; then
        setcap cap_net_raw,cap_net_admin+eip "$PYTHON_PATH" || true
        echo "  BLE ケーパビリティ付与: $PYTHON_PATH"
    fi

    echo "  完了（反映には再ログインが必要）"
else
    echo "  スキップ（root ユーザー）"
fi

echo ""
echo "--- 動作確認 ---"
if $USE_VENV; then
    PYTHON="$VENV_DIR/bin/python3"
else
    PYTHON="python3"
fi

echo -n "  Python: "
"$PYTHON" --version

echo -n "  bless: "
"$PYTHON" -c "import bless; print(getattr(bless, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  Bluetooth: "
hciconfig hci0 2>/dev/null | head -1 || echo "未検出"

echo ""
echo "=========================================="
echo "ライブラリ最小セットアップ完了"
echo ""
echo "次のステップ:"
echo "  - ライブラリのみ利用: そのまま利用可能"
echo "  - LCDサンプルも利用: sudo ./sample/scripts/setup_raspi_sample.sh ${USE_VENV:+--venv ${VENV_DIR}}"
echo "=========================================="
