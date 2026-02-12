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

# 1. システムパッケージ（BlueZのみ）
echo ""
echo "[1/4] BlueZのインストール..."
apt update
apt install -y bluez

# 2. Pythonパッケージ（bless）
echo ""
echo "[2/4] Pythonパッケージのインストール..."
pip install --break-system-packages bless>=0.3.0 || pip install bless>=0.3.0

# 3. Bluetoothサービスの有効化
echo ""
echo "[3/4] Bluetoothサービスの有効化..."
systemctl enable bluetooth
systemctl start bluetooth

# 4. Bluetoothアダプタの状態確認
echo ""
echo "[4/4] Bluetoothアダプタの確認..."
if hciconfig hci0 > /dev/null 2>&1; then
    hciconfig hci0 up
    echo "  hci0: OK"
    hciconfig hci0
else
    echo "  警告: hci0 が見つかりません"
    echo "  Bluetoothハードウェアを確認してください"
fi

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
