#!/bin/bash
#
# Mac エージェント起動スクリプト
#
# キー入力を監視し、BLE 経由で Raspberry Pi に送信する
#
# 使用方法:
#   ./scripts/run_mac.sh              # 対話形式でデバイス選択
#   ./scripts/run_mac.sh RasPi-KeyAgent  # デバイス名を指定して直接接続
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# デバイス名が指定されている場合
if [ -n "$1" ]; then
    PYTHONPATH=src python3 -m ble_sender.main --device "$1"
else
    PYTHONPATH=src python3 -m ble_sender.main
fi
