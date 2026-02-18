#!/bin/bash
#
# Raspberry Pi 環境セットアップスクリプト
#
# BLE GATT サーバー + LCD HAT 表示に必要な
# システムパッケージ、Python パッケージ、ハードウェア設定を一括で行う。
#
# 使用方法:
#   chmod +x scripts/setup_raspi.sh
#   sudo ./scripts/setup_raspi.sh
#
# 対象ハードウェア:
#   - Raspberry Pi (Zero 2W / 3 / 4 / 5)
#   - 1.3inch LCD HAT (ST7789, 240x240, SPI) ※オプション
#
# 参考: https://www.waveshare.com/wiki/1.3inch_LCD_HAT#Python
#

set -e

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi セットアップ"
echo "=========================================="

# root 権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./scripts/setup_raspi.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. システムパッケージ + Python パッケージ (apt)
#    Waveshare wiki 準拠: gpiozero, PIL, numpy, spidev は apt で入れる。
#    pip で入れると apt の lgpio との連携が壊れるため。
echo ""
echo "[1/5] システムパッケージのインストール..."
apt update
apt install -y \
    bluez \
    python3-pip \
    python3-dev \
    python3-gpiozero \
    python3-lgpio \
    python3-spidev \
    python3-pil \
    python3-numpy \
    libopenjp2-7 \
    libtiff6 \
    libatlas3-base \
    libfreetype6-dev

echo "  完了"

# 2. SPI 有効化（LCD HAT 用）
echo ""
echo "[2/5] SPI インターフェースの有効化..."
if raspi-config nonint get_spi | grep -q "1"; then
    raspi-config nonint do_spi 0
    echo "  SPI を有効化しました（再起動後に反映）"
else
    echo "  SPI は既に有効です"
fi

# GPIO プルアップ設定 (Pi 4 以降で必要、LCD HAT ボタン用)
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

PULLUP_LINE="gpio=6,19,5,26,13,21,20,16=pu"
if ! grep -q "$PULLUP_LINE" "$CONFIG_FILE" 2>/dev/null; then
    echo "" >> "$CONFIG_FILE"
    echo "# LCD HAT ボタン用プルアップ設定" >> "$CONFIG_FILE"
    echo "$PULLUP_LINE" >> "$CONFIG_FILE"
    echo "  GPIO プルアップ設定を追加しました"
else
    echo "  GPIO プルアップ設定は既に存在します"
fi

# 3. Python パッケージ (pip) — apt にないものだけ
echo ""
echo "[3/5] BLE ライブラリのインストール (pip)..."

# --break-system-packages フラグ（Debian 12+ / Raspberry Pi OS Bookworm 以降で必要）
PIP_FLAGS=""
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    PIP_FLAGS="--break-system-packages"
fi

# bless のみ pip（apt リポジトリにない BLE GATT サーバーライブラリ）
pip3 install $PIP_FLAGS "bless>=0.3.0"

echo "  完了"

# 4. Bluetooth サービス
echo ""
echo "[4/5] Bluetooth サービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetooth ハードウェアを確認してください"
fi

# 5. 動作確認
echo ""
echo "[5/5] 環境確認..."

echo -n "  Python: "
python3 --version

echo -n "  bless: "
python3 -c "import bless; print(bless.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  Pillow: "
python3 -c "from PIL import Image; print(Image.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  numpy: "
python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "インポートエラー（オプション）"

echo -n "  spidev: "
python3 -c "import spidev; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  gpiozero: "
python3 -c "import gpiozero; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  lgpio: "
python3 -c "import lgpio; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  SPI デバイス: "
if [ -e /dev/spidev0.0 ]; then
    echo "/dev/spidev0.0 OK"
else
    echo "未検出（再起動後に有効）"
fi

echo -n "  Bluetooth: "
hciconfig hci0 2>/dev/null | head -1 || echo "未検出"

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "※ SPI/GPIO 設定を変更した場合は再起動してください:"
echo "  sudo reboot"
echo ""
echo "LCD 表示アプリの起動:"
echo "  cd $PROJECT_ROOT"
echo "  sudo ./scripts/run_raspi.sh"
echo ""
echo "トラブルシューティング:"
echo "  hciconfig              # Bluetooth アダプタ確認"
echo "  ls /dev/spidev*        # SPI デバイス確認"
echo "  journalctl -u bluetooth -f  # Bluetooth ログ"
echo "=========================================="
