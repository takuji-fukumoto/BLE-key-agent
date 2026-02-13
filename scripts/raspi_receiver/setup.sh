#!/bin/bash
#
# Raspberry Pi 環境セットアップスクリプト
#
# BLE GATTサーバー + LCD HAT表示アプリに必要な
# システムパッケージ、Pythonパッケージ、ハードウェア設定を一括で行う。
#
# 使用方法:
#   chmod +x scripts/raspi_receiver/setup.sh
#   sudo ./scripts/raspi_receiver/setup.sh
#
# 対象ハードウェア:
#   - Raspberry Pi (Zero 2W / 3 / 4 / 5)
#   - 1.3inch LCD HAT (ST7789, 240x240, SPI)
#

set -e

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi セットアップ"
echo "=========================================="

# root権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./scripts/raspi_receiver/setup.sh"
    exit 1
fi

ACTUAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 1. システムパッケージ
echo ""
echo "[1/5] システムパッケージのインストール..."
apt update
apt install -y \
    bluez \
    python3-pip \
    python3-dev \
    python3-venv \
    libopenjp2-7 \
    libtiff6 \
    libfreetype6-dev

echo "  完了"

# 2. SPI有効化
echo ""
echo "[2/5] SPI インターフェースの有効化..."
if raspi-config nonint get_spi | grep -q "1"; then
    raspi-config nonint do_spi 0
    echo "  SPI を有効化しました"
else
    echo "  SPI は既に有効です"
fi

# GPIO プルアップ設定 (Pi 4以降で必要)
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

PULLUP_LINE="gpio=6,19,5,26,13,21,20,16=pu"
if ! grep -q "$PULLUP_LINE" "$CONFIG_FILE" 2>/dev/null; then
    echo "" >> "$CONFIG_FILE"
    echo "# LCD HAT ボタン用プルアップ設定" >> "$CONFIG_FILE"
    echo "$PULLUP_LINE" >> "$CONFIG_FILE"
    echo "  GPIO プルアップ設定を追加しました ($CONFIG_FILE)"
else
    echo "  GPIO プルアップ設定は既に存在します"
fi

# 3. Pythonパッケージ
echo ""
echo "[3/5] Pythonパッケージのインストール..."
cd "$PROJECT_ROOT"

if [ -d "venv" ]; then
    echo "  既存の venv を使用します"
else
    echo "  venv を作成中..."
    sudo -u "$ACTUAL_USER" python3 -m venv venv
fi

# venv内にインストール
sudo -u "$ACTUAL_USER" venv/bin/pip install --upgrade pip
sudo -u "$ACTUAL_USER" venv/bin/pip install -e ".[raspi]"

echo "  完了"

# 4. Bluetoothサービス
echo ""
echo "[4/5] Bluetoothサービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetoothハードウェアを確認してください"
fi

# 5. 動作確認
echo ""
echo "[5/5] 環境確認..."

echo -n "  Python: "
venv/bin/python3 --version

echo -n "  bless: "
venv/bin/python3 -c "import bless; print(bless.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  Pillow: "
venv/bin/python3 -c "from PIL import Image; print(Image.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  spidev: "
venv/bin/python3 -c "import spidev; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  gpiozero: "
venv/bin/python3 -c "import gpiozero; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  SPI デバイス: "
if [ -e /dev/spidev0.0 ]; then
    echo "/dev/spidev0.0 OK"
else
    echo "未検出 (再起動後に有効になります)"
fi

echo -n "  Bluetooth: "
hciconfig hci0 2>/dev/null | head -1 || echo "未検出"

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "※ SPI/GPIO設定を変更した場合は再起動してください:"
echo "  sudo reboot"
echo ""
echo "LCD表示アプリの起動:"
echo "  cd $PROJECT_ROOT"
echo "  venv/bin/python -m raspi_receiver.apps.lcd_display.main"
echo ""
echo "テスト実行:"
echo "  venv/bin/pip install -e '.[test]'"
echo "  venv/bin/python -m pytest tests/"
echo ""
echo "トラブルシューティング:"
echo "  hciconfig              # Bluetoothアダプタ確認"
echo "  ls /dev/spidev*        # SPIデバイス確認"
echo "  journalctl -u bluetooth -f  # Bluetoothログ"
echo "=========================================="
