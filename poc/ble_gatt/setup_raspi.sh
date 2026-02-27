#!/bin/bash
#
# Raspberry Pi Zero 2W 用セットアップスクリプト
#
# 使用方法:
#   chmod +x setup_raspi.sh
#   sudo ./setup_raspi.sh              # システムワイドにインストール
#   sudo ./setup_raspi.sh --venv       # venv環境にインストール
#   sudo ./setup_raspi.sh --venv /path/to/venv  # venvパス指定
#

set -e

USE_VENV=false
VENV_DIR="$(cd "$(dirname "$0")" && pwd)/.venv"

# オプション解析
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
            echo "使用方法: sudo ./setup_raspi.sh [--venv [パス]]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "BLE GATT Peripheral セットアップ"
if $USE_VENV; then
    echo "モード: venv ($VENV_DIR)"
else
    echo "モード: システムワイド"
fi
echo "=========================================="

# root権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./setup_raspi.sh"
    exit 1
fi

# 1. システムパッケージ（BlueZのみ）
echo ""
echo "[1/4] BlueZのインストール..."
apt update
apt install -y bluez

# venvの場合はpython3-venvも必要
if $USE_VENV; then
    apt install -y python3-venv
fi

# 2. Pythonパッケージ（bless）
echo ""
echo "[2/4] Pythonパッケージのインストール..."
if $USE_VENV; then
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install "bless>=0.3.0"
else
    pip install --break-system-packages "bless>=0.3.0" || pip install "bless>=0.3.0"
fi

# 3. Bluetoothサービスの有効化
echo ""
echo "[3/4] Bluetoothサービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

# 4. Bluetoothアダプタの状態確認
echo ""
echo "[4/4] Bluetoothアダプタの確認..."
if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
    hciconfig hci0
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetoothハードウェアを確認してください"
fi

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "GATTサーバーの起動:"
if $USE_VENV; then
    echo "  sudo $VENV_DIR/bin/python peripheral_raspi.py"
else
    echo "  sudo python3 peripheral_raspi.py"
fi
echo ""
echo "トラブルシューティング:"
echo "  hciconfig              # アダプタ状態確認"
echo "  sudo hcitool lescan    # BLEスキャン"
echo "  journalctl -u bluetooth -f  # ログ確認"
echo "=========================================="
