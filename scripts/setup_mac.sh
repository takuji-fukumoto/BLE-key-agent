#!/bin/bash
#
# Mac 環境セットアップスクリプト
#
# BLE キーエージェント（Mac側）に必要な Python パッケージをインストール。
# pynput によるキー監視と bleak による BLE 通信を行う。
#
# 使用方法:
#   chmod +x scripts/setup_mac.sh
#   ./scripts/setup_mac.sh
#
# ※ sudo 不要（ユーザー権限でインストール）
#

set -e

echo "=========================================="
echo "BLE Key Agent - Mac セットアップ"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Python バージョン確認
echo ""
echo "[1/3] Python 環境の確認..."
if ! command -v python3 &> /dev/null; then
    echo "エラー: python3 が見つかりません"
    echo "Homebrew でインストールしてください: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYTHON_VERSION"

# バージョンチェック (3.10以上)
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo "エラー: Python 3.10 以上が必要です（現在: $PYTHON_VERSION）"
    exit 1
fi

# 依存パッケージのインストール
echo ""
echo "[2/3] Python パッケージのインストール..."
pip3 install --user bleak>=0.21.0 pynput>=1.7.6

echo "  完了"

# 動作確認
echo ""
echo "[3/3] インストール確認..."

echo -n "  bleak: "
python3 -c "import bleak; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  pynput: "
python3 -c "import pynput; print('OK')" 2>/dev/null || echo "インポートエラー"

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "※ macOS 権限設定（初回のみ）:"
echo "  システム設定 → プライバシーとセキュリティ で"
echo "  ・アクセシビリティ → ターミナル/IDE を許可"
echo "  ・入力監視 → ターミナル/IDE を許可"
echo ""
echo "PoC の実行:"
echo "  cd $PROJECT_ROOT"
echo ""
echo "  # キー監視 PoC"
echo "  python3 poc/pynput/pynput_key_monitor.py"
echo ""
echo "  # BLE Central PoC（Raspberry Pi 起動後に実行）"
echo "  python3 poc/ble_gatt/central_mac.py"
echo "=========================================="
