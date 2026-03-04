#!/bin/bash
#
# UNIHIKER M10 受信サンプル起動スクリプト
#
# BLE で Mac からのキー入力を受信し、UNIHIKER の画面に表示する
#
# 使用方法:
#   ./sample/scripts/run_unihiker.sh [--debug] [--log-dir DIR]
#
# オプション:
#   --debug       DEBUG レベルのログをコンソールに出力
#   --log-dir     ログファイルの出力先ディレクトリ (デフォルト: /tmp/ble-key-agent)
#
# ※ 事前に sample/scripts/setup_unihiker_sample.sh で環境構築済みであること
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# venv が存在すれば自動で有効化
VENV_DIR="$PROJECT_ROOT/.venv"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
    VENV_LABEL="venv ($VENV_DIR)"
else
    # pyenv の Python 3.10+ を検索
    ACTUAL_HOME="${HOME}"
    PYENV_ROOT="${ACTUAL_HOME}/.pyenv"
    FOUND_PYENV=""
    if [ -d "$PYENV_ROOT/versions" ]; then
        for minor in 12 11 10; do
            for pydir in "$PYENV_ROOT/versions/3.${minor}"*/bin/python3; do
                if [ -x "$pydir" ] 2>/dev/null; then
                    FOUND_PYENV="$pydir"
                    break 2
                fi
            done
        done
    fi

    if [ -n "$FOUND_PYENV" ]; then
        PYTHON="$FOUND_PYENV"
        VENV_LABEL="pyenv ($PYTHON)"
    else
        PYTHON="python3"
        VENV_LABEL="system"
    fi
fi

# ログディレクトリのデフォルト値
LOG_DIR="/tmp/ble-key-agent"
for arg in "$@"; do
    if [ "$prev_arg" = "--log-dir" ]; then
        LOG_DIR="$arg"
    fi
    prev_arg="$arg"
done

ensure_bluetooth_discoverable() {
    if ! command -v bluetoothctl >/dev/null 2>&1; then
        echo "警告: bluetoothctl が見つからないため discoverable 設定をスキップします"
        return
    fi

    if bluetoothctl show 2>/dev/null | grep -q "Discoverable: yes"; then
        echo "Bluetooth discoverable: already yes"
        return
    fi

    echo "Bluetooth discoverable を有効化します..."
    if bluetoothctl power on >/dev/null 2>&1 \
        && bluetoothctl pairable on >/dev/null 2>&1 \
        && bluetoothctl discoverable-timeout 0 >/dev/null 2>&1 \
        && bluetoothctl discoverable on >/dev/null 2>&1; then
        echo "Bluetooth discoverable: enabled"
    else
        echo "警告: discoverable 設定に失敗しました。必要に応じて手動で実行してください:"
        echo "   sudo bluetoothctl discoverable on"
    fi
}

ensure_bluetooth_discoverable

echo "=========================================="
echo "BLE Key Agent - UNIHIKER Receiver"
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

PYTHONPATH=src "$PYTHON" -m sample.unihiker_receiver.main "$@"
