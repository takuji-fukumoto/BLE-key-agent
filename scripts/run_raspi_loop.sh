#!/bin/bash
#
# Raspberry Pi LCD アプリ 自動再起動ラッパー
#
# クラッシュ時に自動で再起動する。Ctrl+C で完全停止。
# SSH切断(SIGHUP)では停止しない。
#
# 使用方法:
#   ./scripts/run_raspi_loop.sh [--debug] [--log-dir DIR] [--spi-speed HZ]
#
# バックグラウンド実行 (推奨):
#   nohup ./scripts/run_raspi_loop.sh --debug > /tmp/ble-key-agent/loop.log 2>&1 &
#
# 環境変数:
#   RESTART_DELAY  再起動までの待機秒数 (デフォルト: 3)
#   MAX_RESTARTS   最大連続再起動回数 (デフォルト: 50)
#

# SIGHUP を無視 — SSH切断でスクリプトとPythonプロセスが
# 道連れで死ぬのを防ぐ (trap '' は子プロセスにも継承される)
trap '' HUP

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

RESTART_DELAY="${RESTART_DELAY:-3}"
MAX_RESTARTS="${MAX_RESTARTS:-50}"

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

# ログディレクトリのデフォルト値 (tmpfs でSD書き込み回避)
LOG_DIR="/tmp/ble-key-agent"
for arg in "$@"; do
    if [ "$prev_arg" = "--log-dir" ]; then
        LOG_DIR="$arg"
    fi
    prev_arg="$arg"
done

# ループスクリプト自身のログもファイルに記録
# (SSH切断後もloop.logでスクリプトの動作状況を確認可能)
mkdir -p "$LOG_DIR"
LOOP_LOG="$LOG_DIR/loop.log"

log_msg() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOOP_LOG"
}

ensure_bluetooth_discoverable() {
    if ! command -v bluetoothctl >/dev/null 2>&1; then
        log_msg "⚠️  bluetoothctl が見つからないため discoverable 設定をスキップします"
        return
    fi

    if bluetoothctl show 2>/dev/null | grep -q "Discoverable: yes"; then
        log_msg "Bluetooth discoverable: already yes"
        return
    fi

    log_msg "Bluetooth discoverable を有効化します..."
    if bluetoothctl power on >/dev/null 2>&1 \
        && bluetoothctl pairable on >/dev/null 2>&1 \
        && bluetoothctl discoverable-timeout 0 >/dev/null 2>&1 \
        && bluetoothctl discoverable on >/dev/null 2>&1; then
        log_msg "Bluetooth discoverable: enabled"
    else
        log_msg "⚠️  discoverable 設定に失敗しました。必要に応じて手動で実行してください: sudo bluetoothctl discoverable on"
    fi
}

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi LCD App"
echo "  (auto-restart mode)"
echo "=========================================="
echo ""
echo "Python: $PYTHON ($VENV_LABEL)"
echo "ログ出力: $LOG_DIR/raspi_receiver.log"
echo "ループログ: $LOOP_LOG"
echo "クラッシュログ: $LOG_DIR/crash.log"
echo "再起動間隔: ${RESTART_DELAY}s / 最大連続再起動: ${MAX_RESTARTS}"
echo ""
echo "終了するには Ctrl+C を押してください"
echo "(SSH切断では停止しません)"
echo "=========================================="
echo ""

log_msg "Loop script started (PID=$$)"

restart_count=0
user_interrupted=false

trap 'user_interrupted=true' INT TERM

while true; do
    ensure_bluetooth_discoverable
    log_msg "アプリを起動します (restart #${restart_count})..."

    PYTHONPATH=src "$PYTHON" -m raspi_receiver.apps.lcd_display.main "$@"
    exit_code=$?

    # Ctrl+C による終了
    if $user_interrupted; then
        log_msg "ユーザーにより停止しました"
        exit 0
    fi

    restart_count=$((restart_count + 1))

    # exit code の解釈
    if [ "$exit_code" -gt 128 ]; then
        signal_num=$((exit_code - 128))
        exit_reason="exit code: ${exit_code} (killed by signal ${signal_num})"
    else
        exit_reason="exit code: ${exit_code}"
    fi

    log_msg "プロセスが終了しました (${exit_reason})"

    # 再起動ログをファイルに記録
    mkdir -p "$LOG_DIR"
    echo "$(date '+%Y-%m-%d %H:%M:%S') RESTART #${restart_count}: ${exit_reason}" >> "$LOG_DIR/restart.log"

    # crash.log があれば表示
    if [ -f "$LOG_DIR/crash.log" ]; then
        echo "--- crash.log (last 10 lines) ---"
        tail -10 "$LOG_DIR/crash.log"
        echo "---------------------------------"
    fi

    # 最大再起動回数チェック
    if [ "$restart_count" -ge "$MAX_RESTARTS" ]; then
        log_msg "最大再起動回数 (${MAX_RESTARTS}) に達しました。停止します。"
        exit 1
    fi

    log_msg "${RESTART_DELAY}秒後に再起動します..."
    sleep "$RESTART_DELAY"

    # SPI/GPIO デバイスのリセット (クラッシュ後の不正状態を解消)
    if [ -e /dev/spidev0.0 ]; then
        log_msg "SPI デバイスをリセット中..."
        # spidev を unbind → rebind してハードウェア状態をクリア
        for spi_dev in /sys/bus/spi/drivers/spidev/spi*; do
            if [ -e "$spi_dev" ]; then
                dev_name=$(basename "$spi_dev")
                echo "$dev_name" | sudo tee /sys/bus/spi/drivers/spidev/unbind 2>/dev/null || true
                sleep 0.5
                echo "$dev_name" | sudo tee /sys/bus/spi/drivers/spidev/bind 2>/dev/null || true
            fi
        done
        sleep 1
    fi

    # GPIO ピンを解放 (gpiozero のロック解除)
    if [ -d /sys/class/gpio ]; then
        for pin in 24 25; do
            if [ -e "/sys/class/gpio/gpio${pin}" ]; then
                echo "$pin" | sudo tee /sys/class/gpio/unexport 2>/dev/null || true
            fi
        done
    fi

    # bluetooth デーモンを再起動 (クリーンな状態にする)
    if command -v systemctl &>/dev/null; then
        log_msg "bluetooth サービスを再起動中..."
        sudo systemctl restart bluetooth || true
        sleep 2
    fi
done
