#!/bin/bash
#
# Raspberry Pi Zero 2W 用セットアップスクリプト
#
# 使用方法:
#   chmod +x setup_raspi.sh
#   sudo ./setup_raspi.sh
#

set -e

echo "=========================================="
echo "BLE GATT Peripheral セットアップ"
echo "=========================================="

# root権限チェック
if [ "$EUID" -ne 0 ]; then
    echo "sudo で実行してください: sudo ./setup_raspi.sh"
    exit 1
fi

# 1. 必要パッケージのインストール
echo ""
echo "[1/4] パッケージのインストール..."
apt update
apt install -y python3-dbus python3-gi bluez

# 2. Bluetoothサービスの有効化
echo ""
echo "[2/4] Bluetoothサービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

# 3. Bluetoothアダプタの状態確認
echo ""
echo "[3/4] Bluetoothアダプタの確認..."
if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
    hciconfig hci0
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetoothハードウェアを確認してください"
fi

# 4. BlueZ設定の更新（BLE Peripheral用）
echo ""
echo "[4/4] BlueZ設定の更新..."
MAIN_CONF="/etc/bluetooth/main.conf"
if [ -f "$MAIN_CONF" ]; then
    # バックアップ
    cp "$MAIN_CONF" "${MAIN_CONF}.bak"
fi

# Experimental機能の有効化（GATTサーバーに必要な場合がある）
if grep -q "^#.*Experimental" "$MAIN_CONF" 2>/dev/null; then
    sed -i 's/^#.*Experimental.*/Experimental = true/' "$MAIN_CONF"
elif ! grep -q "^Experimental" "$MAIN_CONF" 2>/dev/null; then
    echo "" >> "$MAIN_CONF"
    echo "[General]" >> "$MAIN_CONF"
    echo "Experimental = true" >> "$MAIN_CONF"
fi

# サービス再起動
systemctl restart bluetooth
sleep 2

echo ""
echo "=========================================="
echo "セットアップ完了"
echo ""
echo "GATTサーバーの起動:"
echo "  sudo python3 peripheral_raspi.py"
echo ""
echo "トラブルシューティング:"
echo "  hciconfig              # アダプタ状態確認"
echo "  sudo hcitool lescan    # BLEスキャン"
echo "  journalctl -u bluetooth -f  # ログ確認"
echo "=========================================="
