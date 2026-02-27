#!/bin/bash
#
# Raspberry Pi LCD 表示アプリ起動スクリプト
#
# BLE で Mac からのキー入力を受信し、LCD に表示する
#
# 使用方法:
#   ./scripts/run_raspi.sh [--debug] [--log-dir DIR] [--spi-speed HZ]
#
# オプション:
#   --debug       DEBUG レベルのログをコンソールに出力
#   --log-dir     ログファイルの出力先ディレクトリ (デフォルト: logs/)
#   --spi-speed   SPI バス速度 (Hz, デフォルト: 20000000)
#
# ※ 事前に setup_raspi.sh で権限設定済みであること
#   （BLE ケーパビリティ + bluetooth/spi/gpio グループ）
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# venv が存在すれば自動で有効化
VENV_DIR="$PROJECT_ROOT/.venv"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
    VENV_LABEL="venv ($VENV_DIR)"
else
    PYTHON="python3"
    VENV_LABEL="system"
fi

# ログディレクトリのデフォルト値
LOG_DIR="logs"
for arg in "$@"; do
    if [ "$prev_arg" = "--log-dir" ]; then
        LOG_DIR="$arg"
    fi
    prev_arg="$arg"
done

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi LCD App"
echo "=========================================="
echo ""
echo "Python: $PYTHON ($VENV_LABEL)"
echo "ログ出力: $LOG_DIR/raspi_receiver.log"
echo "BLE アドバタイズを開始します..."
echo "デバイス名: RasPi-KeyAgent"
echo ""
echo "終了するには Ctrl+C を押してください"
echo "=========================================="
echo ""

PYTHONPATH=src "$PYTHON" -m raspi_receiver.apps.lcd_display.main "$@"
