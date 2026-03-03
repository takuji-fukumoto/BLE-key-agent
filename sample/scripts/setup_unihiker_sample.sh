#!/bin/bash
#
# UNIHIKER M10 サンプルセットアップスクリプト
#
# UNIHIKER 向け受信サンプル (sample/unihiker_receiver) の実行に必要な
# Python / BLE 依存をセットアップする。
#
# 使用方法:
#   chmod +x sample/scripts/setup_unihiker_sample.sh
#   sudo ./sample/scripts/setup_unihiker_sample.sh
#   sudo ./sample/scripts/setup_unihiker_sample.sh --venv
#   sudo ./sample/scripts/setup_unihiker_sample.sh --venv /path/to/venv
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

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
            echo "使用方法: sudo ./sample/scripts/setup_unihiker_sample.sh [--venv [パス]]"
            exit 1
            ;;
    esac
done

if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./sample/scripts/setup_unihiker_sample.sh"
    exit 1
fi

echo "=========================================="
echo "BLE Key Agent - UNIHIKER Sample Setup"
if $USE_VENV; then
    echo "モード: venv ($VENV_DIR)"
else
    echo "モード: システムワイド"
fi
echo "=========================================="

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
echo "[2/4] Python パッケージをインストール..."
ACTUAL_USER="${SUDO_USER:-$USER}"

if $USE_VENV; then
    SYSTEM_PYTHON="/usr/bin/python3"
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install "bless>=0.3.0" "unihiker"

    if [ "$ACTUAL_USER" != "root" ]; then
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$VENV_DIR"
    fi
    PYTHON_PATH="$(readlink -f "$VENV_DIR/bin/python3")"
else
    PIP_FLAGS=""
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PIP_FLAGS="--break-system-packages"
    fi
    pip3 install $PIP_FLAGS "bless>=0.3.0" "unihiker"
    PYTHON_PATH="$(readlink -f "$(which python3)")"
fi

echo "  完了"

echo ""
echo "[3/4] Bluetooth サービス設定..."
systemctl enable bluetooth || true
systemctl start bluetooth || true

if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
    bluetoothctl pairable on >/dev/null 2>&1 || true
    bluetoothctl discoverable-timeout 0 >/dev/null 2>&1 || true
    bluetoothctl discoverable on >/dev/null 2>&1 || true
fi

if hciconfig hci0 >/dev/null 2>&1; then
    hciconfig hci0 up || true
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
fi

echo "  完了"

echo ""
echo "[4/4] 非 root 実行向け権限設定と動作確認..."
if [ "$ACTUAL_USER" != "root" ]; then
    usermod -aG bluetooth "$ACTUAL_USER" 2>/dev/null || true
    if [ -n "$PYTHON_PATH" ]; then
        setcap cap_net_raw,cap_net_admin+eip "$PYTHON_PATH" || true
    fi
fi

if $USE_VENV; then
    PYTHON="$VENV_DIR/bin/python3"
else
    PYTHON="python3"
fi

echo -n "  Python: "
"$PYTHON" --version

echo -n "  bless: "
"$PYTHON" -c "import bless; print(getattr(bless, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  unihiker: "
"$PYTHON" -c "import unihiker; print(getattr(unihiker, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  tkinter: "
"$PYTHON" -c "import tkinter; print('OK')" 2>/dev/null || echo "インポートエラー"

echo ""
echo "=========================================="
echo "UNIHIKER サンプルセットアップ完了"
echo ""
echo "起動方法:"
echo "  $PYTHON -m sample.unihiker_receiver.main"
echo "=========================================="
