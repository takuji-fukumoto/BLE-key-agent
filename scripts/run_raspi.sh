#!/bin/bash
#
# Raspberry Pi LCD 表示アプリ起動スクリプト
#
# BLE で Mac からのキー入力を受信し、LCD に表示する
#
# 使用方法:
#   sudo ./scripts/run_raspi.sh
#
# ※ BLE アドバタイズと GPIO/SPI アクセスのため sudo が必要
#

set -e

# root 権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./scripts/run_raspi.sh"
    exit 1
fi

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
