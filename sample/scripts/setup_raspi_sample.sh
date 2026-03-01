#!/bin/bash
#
# Raspberry Pi LCD サンプルセットアップスクリプト
#
# sample/ 配下の LCD サンプルを動かすための追加セットアップ。
# 先に scripts/setup_raspi.sh（ライブラリ最小）を実行し、
# その上に LCD/SPI/GPIO 依存を追加する。
#
# 使用方法:
#   chmod +x sample/scripts/setup_raspi_sample.sh
#   sudo ./sample/scripts/setup_raspi_sample.sh
#   sudo ./sample/scripts/setup_raspi_sample.sh --venv
#   sudo ./sample/scripts/setup_raspi_sample.sh --venv /path/to/venv
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./sample/scripts/setup_raspi_sample.sh"
    exit 1
fi

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi LCD Sample Setup"
echo "=========================================="

echo ""
echo "[1/4] ライブラリ最小セットアップを実行..."
"$PROJECT_ROOT/scripts/setup_raspi.sh" "$@"

echo ""
echo "[2/4] LCD/SPI/GPIO 依存パッケージをインストール..."
apt update
apt install -y \
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

echo ""
echo "[3/4] SPI と GPIO pull-up を設定..."
if command -v raspi-config >/dev/null 2>&1; then
    if raspi-config nonint get_spi | grep -q "1"; then
        raspi-config nonint do_spi 0
        echo "  SPI を有効化しました（再起動後に反映）"
    else
        echo "  SPI は既に有効です"
    fi
else
    echo "  警告: raspi-config が見つかりません。SPI設定をスキップします"
fi

CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

PULLUP_LINE="gpio=6,19,5,26,13,21,20,16=pu"
if ! grep -q "$PULLUP_LINE" "$CONFIG_FILE" 2>/dev/null; then
    {
        echo ""
        echo "# LCD HAT ボタン用プルアップ設定"
        echo "$PULLUP_LINE"
    } >> "$CONFIG_FILE"
    echo "  GPIO プルアップ設定を追加しました"
else
    echo "  GPIO プルアップ設定は既に存在します"
fi

echo ""
echo "[4/4] LCD サンプル依存を確認..."
echo -n "  Pillow: "
python3 -c "from PIL import Image; print(Image.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  numpy: "
python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  spidev: "
python3 -c "import spidev; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  gpiozero: "
python3 -c "import gpiozero; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  SPI デバイス: "
if [ -e /dev/spidev0.0 ]; then
    echo "/dev/spidev0.0 OK"
else
    echo "未検出（再起動後に有効）"
fi

echo ""
echo "=========================================="
echo "LCD サンプルセットアップ完了"
echo ""
echo "※ SPI/GPIO 設定反映のため再起動を推奨:"
echo "  sudo reboot"
echo ""
echo "起動方法:"
echo "  ./sample/scripts/run_raspi.sh"
echo "=========================================="
