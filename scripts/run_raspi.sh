#!/bin/bash
#
# Raspberry Pi LCD 表示アプリ起動スクリプト
#
# BLE で Mac からのキー入力を受信し、LCD に表示する
#
# 使用方法:
#   ./scripts/run_raspi.sh
#
# ※ 事前に setup_raspi.sh で権限設定済みであること
#   （BLE ケーパビリティ + bluetooth/spi/gpio グループ）
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi LCD App"
echo "=========================================="
echo ""
echo "BLE アドバタイズを開始します..."
echo "デバイス名: RasPi-KeyAgent"
echo ""
echo "終了するには Ctrl+C を押してください"
echo "=========================================="
echo ""

PYTHONPATH=src python3 -m raspi_receiver.apps.lcd_display.main
