#!/bin/bash
#
# Raspberry Pi LCD アプリ 自動再起動ラッパー
#
# クラッシュ時に自動で再起動する。Ctrl+C で完全停止。
#
# 使用方法:
#   ./scripts/run_raspi_loop.sh [--debug] [--log-dir DIR] [--spi-speed HZ]
#
# 環境変数:
#   RESTART_DELAY  再起動までの待機秒数 (デフォルト: 3)
#   MAX_RESTARTS   最大連続再起動回数 (デフォルト: 50)
#

set -e

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
echo "  (auto-restart mode)"
echo "=========================================="
echo ""
echo "Python: $PYTHON ($VENV_LABEL)"
echo "ログ出力: $LOG_DIR/raspi_receiver.log"
echo "クラッシュログ: $LOG_DIR/crash.log"
echo "再起動間隔: ${RESTART_DELAY}s / 最大連続再起動: ${MAX_RESTARTS}"
echo ""
echo "終了するには Ctrl+C を押してください"
echo "=========================================="
echo ""

restart_count=0
user_interrupted=false

trap 'user_interrupted=true' INT TERM

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] アプリを起動します (restart #${restart_count})..."

    # set +e で終了コードを取得
    set +e
    PYTHONPATH=src "$PYTHON" -m raspi_receiver.apps.lcd_display.main "$@"
    exit_code=$?
    set -e

    # Ctrl+C による終了
    if $user_interrupted; then
        echo ""
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ユーザーにより停止しました"
        exit 0
    fi

    restart_count=$((restart_count + 1))

    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] プロセスが終了しました (exit code: ${exit_code})"

    # crash.log があれば表示
    if [ -f "$LOG_DIR/crash.log" ]; then
        echo "--- crash.log (last 10 lines) ---"
        tail -10 "$LOG_DIR/crash.log"
        echo "---------------------------------"
    fi

    # 最大再起動回数チェック
    if [ "$restart_count" -ge "$MAX_RESTARTS" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 最大再起動回数 (${MAX_RESTARTS}) に達しました。停止します。"
        exit 1
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${RESTART_DELAY}秒後に再起動します..."
    sleep "$RESTART_DELAY"

    # bluetooth デーモンを再起動 (クリーンな状態にする)
    if command -v systemctl &>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] bluetooth サービスを再起動中..."
        sudo systemctl restart bluetooth
        sleep 2
    fi
done
