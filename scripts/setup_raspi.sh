#!/bin/bash
#
# Raspberry Pi 環境セットアップスクリプト
#
# BLE GATT サーバー + LCD HAT 表示に必要な
# システムパッケージ、Python パッケージ、ハードウェア設定を一括で行う。
#
# 使用方法:
#   chmod +x scripts/setup_raspi.sh
#   sudo ./scripts/setup_raspi.sh              # システムワイドにインストール
#   sudo ./scripts/setup_raspi.sh --venv       # venv環境にインストール（推奨）
#   sudo ./scripts/setup_raspi.sh --venv /path/to/venv  # venvパス指定
#
# 対象ハードウェア:
#   - Raspberry Pi (Zero 2W / 3 / 4 / 5)
#   - 1.3inch LCD HAT (ST7789, 240x240, SPI) ※オプション
#
# 参考: https://www.waveshare.com/wiki/1.3inch_LCD_HAT#Python
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

USE_VENV=false
VENV_DIR="$PROJECT_ROOT/.venv"

# オプション解析
while [ $# -gt 0 ]; do
    case "$1" in
        --venv)
            USE_VENV=true
            if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
                VENV_DIR="$2"
                shift
            fi
            shift
            ;;
        *)
            echo "不明なオプション: $1"
            echo "使用方法: sudo ./scripts/setup_raspi.sh [--venv [パス]]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "BLE Key Agent - Raspberry Pi セットアップ"
if $USE_VENV; then
    echo "モード: venv ($VENV_DIR)"
else
    echo "モード: システムワイド"
fi
echo "=========================================="

# root 権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./scripts/setup_raspi.sh"
    exit 1
fi

# IPv6 でリポジトリに接続できない環境向けに IPv4 を強制
APT_CONF="/etc/apt/apt.conf.d/99force-ipv4"
if [ ! -f "$APT_CONF" ]; then
    echo 'Acquire::ForceIPv4 "true";' > "$APT_CONF"
    echo "  IPv4 強制設定を追加: $APT_CONF"
fi

# 1. システムパッケージ + Python パッケージ (apt)
#    Waveshare wiki 準拠: gpiozero, PIL, spidev は apt で入れる。
#    pip で入れると apt の lgpio との連携が壊れるため。
echo ""
echo "[1/6] システムパッケージのインストール..."
apt update
apt install -y \
    bluez \
    python3-pip \
    python3-dev \
    python3-gpiozero \
    python3-lgpio \
    python3-spidev \
    python3-pil \
    libopenjp2-7 \
    libtiff6 \
    libatlas3-base \
    libfreetype6-dev

if $USE_VENV; then
    apt install -y python3-venv
fi

echo "  完了"

# 2. SPI 有効化（LCD HAT 用）
echo ""
echo "[2/6] SPI インターフェースの有効化..."
if raspi-config nonint get_spi | grep -q "1"; then
    raspi-config nonint do_spi 0
    echo "  SPI を有効化しました（再起動後に反映）"
else
    echo "  SPI は既に有効です"
fi

# GPIO プルアップ設定 (Pi 4 以降で必要、LCD HAT ボタン用)
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

PULLUP_LINE="gpio=6,19,5,26,13,21,20,16=pu"
if ! grep -q "$PULLUP_LINE" "$CONFIG_FILE" 2>/dev/null; then
    echo "" >> "$CONFIG_FILE"
    echo "# LCD HAT ボタン用プルアップ設定" >> "$CONFIG_FILE"
    echo "$PULLUP_LINE" >> "$CONFIG_FILE"
    echo "  GPIO プルアップ設定を追加しました"
else
    echo "  GPIO プルアップ設定は既に存在します"
fi

# 3. Python パッケージ (pip) — apt にないものだけ
echo ""
echo "[3/6] BLE ライブラリのインストール (pip)..."

if $USE_VENV; then
    # venv 作成（--system-site-packages で apt の Python パッケージを引き継ぐ）
    # gpiozero, lgpio, spidev, PIL 等は apt 版を使う必要があるため
    # /usr/bin/python3 を明示的に使用（/usr/local/bin に別バージョンがあると
    # apt パッケージと Python バージョンが不一致になるため）
    ACTUAL_USER="${SUDO_USER:-$USER}"
    SYSTEM_PYTHON="/usr/bin/python3"
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install "bless>=0.3.0"

    # venv の所有者を実行ユーザーに変更（sudo で作成されるため）
    if [ "$ACTUAL_USER" != "root" ]; then
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$VENV_DIR"
    fi
else
    # --break-system-packages フラグ（Debian 12+ / Raspberry Pi OS Bookworm 以降で必要）
    PIP_FLAGS=""
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PIP_FLAGS="--break-system-packages"
    fi

    # bless のみ pip（apt リポジトリにない BLE GATT サーバーライブラリ）
    pip3 install $PIP_FLAGS "bless>=0.3.0"
fi

echo "  完了"

# 4. Bluetooth サービス
echo ""
echo "[4/6] Bluetooth サービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetooth ハードウェアを確認してください"
fi

# 5. sudo なし実行のための権限設定
echo ""
echo "[5/6] ユーザー権限の設定（sudo なし実行用）..."

# SUDO_USER: sudo 経由で実行した場合の元ユーザー
ACTUAL_USER="${SUDO_USER:-$USER}"

if [ "$ACTUAL_USER" != "root" ]; then
    # BLE / GPIO / SPI グループに追加
    usermod -aG bluetooth "$ACTUAL_USER" 2>/dev/null && echo "  bluetooth グループに追加" || true
    usermod -aG spi "$ACTUAL_USER" 2>/dev/null && echo "  spi グループに追加" || true
    usermod -aG gpio "$ACTUAL_USER" 2>/dev/null && echo "  gpio グループに追加" || true

    # Python に BLE ケーパビリティを付与（sudo なしで BLE 操作可能にする）
    if $USE_VENV; then
        PYTHON_PATH="$(readlink -f "$VENV_DIR/bin/python3")"
    else
        PYTHON_PATH="$(readlink -f "$(which python3)")"
    fi
    if [ -n "$PYTHON_PATH" ]; then
        setcap cap_net_raw,cap_net_admin+eip "$PYTHON_PATH"
        echo "  BLE ケーパビリティを付与: $PYTHON_PATH"
    else
        echo "  警告: python3 のパスが取得できません"
    fi

    echo "  完了（反映には再ログインが必要です）"
else
    echo "  スキップ（root ユーザーのため）"
fi

# 6. 動作確認
echo ""
echo "[6/6] 環境確認..."

if $USE_VENV; then
    PYTHON="$VENV_DIR/bin/python3"
else
    PYTHON="python3"
fi

echo -n "  Python: "
"$PYTHON" --version

echo -n "  bless: "
"$PYTHON" -c "import bless; print(getattr(bless, '__version__', 'OK'))" 2>/dev/null || echo "インポートエラー"

echo -n "  Pillow: "
"$PYTHON" -c "from PIL import Image; print(Image.__version__)" 2>/dev/null || echo "インポートエラー"

echo -n "  spidev: "
"$PYTHON" -c "import spidev; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  gpiozero: "
"$PYTHON" -c "import gpiozero; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  lgpio: "
"$PYTHON" -c "import lgpio; print('OK')" 2>/dev/null || echo "インポートエラー"

echo -n "  SPI デバイス: "
if [ -e /dev/spidev0.0 ]; then
    echo "/dev/spidev0.0 OK"
else
    echo "未検出（再起動後に有効）"
fi

echo -n "  Bluetooth: "
hciconfig hci0 2>/dev/null | head -1 || echo "未検出"

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "※ SPI/GPIO/権限 設定を反映するため再起動してください:"
echo "  sudo reboot"
echo ""
echo "LCD 表示アプリの起動（sudo 不要）:"
echo "  cd $PROJECT_ROOT"
if $USE_VENV; then
    echo "  ./scripts/run_raspi.sh          # venv は自動検出されます"
else
    echo "  ./scripts/run_raspi.sh"
fi
echo ""
echo "トラブルシューティング:"
echo "  hciconfig              # Bluetooth アダプタ確認"
echo "  ls /dev/spidev*        # SPI デバイス確認"
echo "  journalctl -u bluetooth -f  # Bluetooth ログ"
echo "  groups                 # グループ確認"
echo "=========================================="
