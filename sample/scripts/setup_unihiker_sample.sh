#!/bin/bash
#
# UNIHIKER M10 サンプルセットアップスクリプト
#
# UNIHIKER 向け受信サンプル (sample/unihiker_receiver) の実行に必要な
# Python / BLE 依存をセットアップする。
#
# 使用方法:
#   chmod +x sample/scripts/setup_unihiker_sample.sh
#   sudo ./sample/scripts/setup_unihiker_sample.sh
#   sudo ./sample/scripts/setup_unihiker_sample.sh --venv
#   sudo ./sample/scripts/setup_unihiker_sample.sh --venv /path/to/venv
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

USE_VENV=false
VENV_DIR="$PROJECT_ROOT/.venv"

while [ $# -gt 0 ]; do
    case "$1" in
        --venv)
            USE_VENV=true
            if [ -n "$2" ] && case "$2" in -*) false;; *) true;; esac; then
                VENV_DIR="$2"
                shift
            fi
            shift
            ;;
        *)
            echo "不明なオプション: $1"
            echo "使用方法: sudo ./sample/scripts/setup_unihiker_sample.sh [--venv [パス]]"
            exit 1
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./sample/scripts/setup_unihiker_sample.sh"
    exit 1
fi

echo "=========================================="
echo "BLE Key Agent - UNIHIKER Sample Setup"
if $USE_VENV; then
    echo "モード: venv ($VENV_DIR)"
else
    echo "モード: システムワイド"
fi
echo "=========================================="

echo ""
echo "[1/5] 必須システムパッケージをインストール..."
if ! apt update 2>&1; then
    echo ""
    echo "  警告: apt update に失敗しました。"
    echo "  Debian Buster 等の古いディストリビューションではリポジトリが"
    echo "  アーカイブに移行されている場合があります。"
    echo ""
    echo "  以下の手順で修正してください:"
    echo ""
    echo "  1) /etc/apt/sources.list を書き換え:"
    echo "    sudo cp /etc/apt/sources.list /etc/apt/sources.list.backup"
    echo "    sudo tee /etc/apt/sources.list << 'EOF'"
    echo "    deb http://archive.debian.org/debian/ buster main contrib non-free"
    echo "    deb http://archive.debian.org/debian/ buster-updates main contrib non-free"
    echo "    deb http://archive.debian.org/debian-security buster/updates main contrib non-free"
    echo "    EOF"
    echo ""
    echo "  2) Release ファイルの有効期限チェックを無効化:"
    echo "    echo 'Acquire::Check-Valid-Until \"false\";' | sudo tee /etc/apt/apt.conf.d/99no-check-valid-until"
    echo ""
    echo "  修正後、再度このスクリプトを実行してください。"
    exit 1
fi
apt install -y \
    bluez \
    python3-pip \
    python3-dev \
    libcap2-bin

if $USE_VENV; then
    apt install -y python3-venv
fi

echo "  完了"

echo ""
echo "[2/5] Python 3.10+ を検出..."
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")
MIN_PYTHON_MINOR=10

# Python 3.10+ のバイナリを探す
find_suitable_python() {
    # 1) pyenv のバージョンを検索（3.12 → 3.11 → 3.10 の順で優先）
    PYENV_ROOT="${ACTUAL_HOME}/.pyenv"
    if [ -d "$PYENV_ROOT/versions" ]; then
        for minor in 12 11 10; do
            for pydir in "$PYENV_ROOT/versions/3.${minor}"*/bin/python3; do
                if [ -x "$pydir" ] 2>/dev/null; then
                    echo "$pydir"
                    return 0
                fi
            done
        done
    fi

    # 2) システム python3 が 3.10+ か確認
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_PYTHON_MINOR) else 1)" 2>/dev/null; then
            echo "$(command -v python3)"
            return 0
        fi
    fi

    return 1
}

FOUND_PYTHON="$(find_suitable_python)" || true

if [ -z "$FOUND_PYTHON" ]; then
    echo ""
    echo "  エラー: Python 3.10+ が見つかりません。"
    echo "  このプロジェクトは Python 3.10 以上が必要です。"
    echo ""
    echo "  UNIHIKER では pyenv で Python 3.11 をインストールできます:"
    echo ""
    echo "  方法A) プリビルド版を使用（推奨・高速）:"
    echo "    git clone https://github.com/liliang9693/unihiker-pyenv-python.git"
    echo "    cd unihiker-pyenv-python"
    echo "    chmod +x install.sh && ./install.sh"
    echo ""
    echo "  方法B) pyenv で手動ビルド:"
    echo "    curl https://pyenv.run | bash"
    echo "    # ~/.bashrc に pyenv 設定を追加後:"
    echo "    pyenv install 3.11.4"
    echo ""
    echo "  インストール後、再度このスクリプトを実行してください。"
    exit 1
fi

echo "  検出: $FOUND_PYTHON ($("$FOUND_PYTHON" --version 2>&1))"

echo ""
echo "[3/5] Python パッケージをインストール..."

if $USE_VENV; then
    "$FOUND_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install "bless>=0.3.0" "unihiker"

    if [ "$ACTUAL_USER" != "root" ]; then
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$VENV_DIR"
    fi
    PYTHON_PATH="$(readlink -f "$VENV_DIR/bin/python3")"
else
    PIP_FLAGS=""
    if "$FOUND_PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PIP_FLAGS="--break-system-packages"
    fi
    "$FOUND_PYTHON" -m pip install $PIP_FLAGS "bless>=0.3.0" "unihiker"
    PYTHON_PATH="$(readlink -f "$FOUND_PYTHON")"
fi

echo "  完了"

echo ""
echo "[4/5] Bluetooth サービス設定..."
systemctl enable bluetooth || true
systemctl start bluetooth || true

if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
    bluetoothctl pairable on >/dev/null 2>&1 || true
    bluetoothctl discoverable-timeout 0 >/dev/null 2>&1 || true
    bluetoothctl discoverable on >/dev/null 2>&1 || true
fi

if hciconfig hci0 >/dev/null 2>&1; then
    hciconfig hci0 up || true
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
fi

echo "  完了"

echo ""
echo "[5/5] 非 root 実行向け権限設定と動作確認..."
if [ "$ACTUAL_USER" != "root" ]; then
    usermod -aG bluetooth "$ACTUAL_USER" 2>/dev/null || true
    if [ -n "$PYTHON_PATH" ]; then
        setcap cap_net_raw,cap_net_admin+eip "$PYTHON_PATH" || true
    fi
fi

if $USE_VENV; then
    PYTHON="$VENV_DIR/bin/python3"
else
    PYTHON="$FOUND_PYTHON"
fi

echo -n "  Python: "
"$PYTHON" --version

echo -n "  bless: "
"$PYTHON" -c "import bless; print(getattr(bless, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  unihiker: "
"$PYTHON" -c "import unihiker; print(getattr(unihiker, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  tkinter: "
"$PYTHON" -c "import tkinter; print('OK')" 2>/dev/null || echo "インポートエラー"

echo ""
echo "=========================================="
echo "UNIHIKER サンプルセットアップ完了"
echo ""
echo "起動方法:"
echo "  $PYTHON -m sample.unihiker_receiver.main"
echo "=========================================="
