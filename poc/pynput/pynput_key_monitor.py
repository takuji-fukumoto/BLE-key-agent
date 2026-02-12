#!/usr/bin/env python3
"""
pynput によるキー入力監視 PoC (macOS対応)

機能:
- グローバルキーボード入力の監視
- 修飾キー（Cmd, Ctrl, Alt, Shift）の状態追跡
- 特殊キーと通常キーの識別
- asyncio との連携（キューベース）

使用方法:
    python pynput_key_monitor.py

終了:
    Escキーを押す

注意:
    macOSでは「システム設定 → プライバシーとセキュリティ → アクセシビリティ」で
    ターミナルまたはIDEへの権限付与が必要です。
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

from pynput import keyboard


class KeyType(Enum):
    """キーの種類を表すEnum"""
    CHAR = "char"           # 通常の文字キー
    SPECIAL = "special"     # 特殊キー（Enter, Space等）
    MODIFIER = "modifier"   # 修飾キー（Cmd, Ctrl等）


@dataclass
class KeyEvent:
    """キーイベントを表すデータクラス"""
    key_type: KeyType
    key_value: str
    is_press: bool  # True=押下, False=解放
    modifiers: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        action = "Press" if self.is_press else "Release"
        mod_str = ""
        active_mods = [k for k, v in self.modifiers.items() if v]
        if active_mods:
            mod_str = f"[{'+'.join(active_mods)}] "
        return f"{action}: {mod_str}{self.key_value} ({self.key_type.value})"


class KeyMonitor:
    """
    キーボード入力を監視するクラス
    
    pynputのListenerをラップし、修飾キーの状態管理と
    asyncioとの連携機能を提供します。
    """
    
    # 修飾キーのマッピング
    MODIFIER_KEYS = {
        keyboard.Key.shift: 'shift',
        keyboard.Key.shift_l: 'shift',
        keyboard.Key.shift_r: 'shift',
        keyboard.Key.ctrl: 'ctrl',
        keyboard.Key.ctrl_l: 'ctrl',
        keyboard.Key.ctrl_r: 'ctrl',
        keyboard.Key.alt: 'alt',
        keyboard.Key.alt_l: 'alt',
        keyboard.Key.alt_r: 'alt',
        keyboard.Key.cmd: 'cmd',
        keyboard.Key.cmd_l: 'cmd',
        keyboard.Key.cmd_r: 'cmd',
    }
    
    def __init__(self, 
                 on_key_event: Optional[Callable[[KeyEvent], None]] = None,
                 stop_key: keyboard.Key = keyboard.Key.esc):
        """
        Args:
            on_key_event: キーイベント発生時のコールバック関数
            stop_key: 監視を停止するキー（デフォルト: Esc）
        """
        self.on_key_event = on_key_event
        self.stop_key = stop_key
        self._listener: Optional[keyboard.Listener] = None
        self._running = False
        
        # 修飾キーの状態
        self._modifiers = {
            'shift': False,
            'ctrl': False,
            'alt': False,
            'cmd': False,
        }
        
        # asyncio連携用
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[asyncio.Queue] = None
    
    @property
    def modifiers(self) -> dict:
        """現在の修飾キーの状態を返す"""
        return self._modifiers.copy()
    
    def _classify_key(self, key) -> tuple[KeyType, str]:
        """キーを分類し、種類と文字列表現を返す"""
        # 修飾キーかチェック
        if key in self.MODIFIER_KEYS:
            return KeyType.MODIFIER, self.MODIFIER_KEYS[key]
        
        # 通常の文字キーかチェック
        if isinstance(key, keyboard.KeyCode):
            if key.char is not None:
                return KeyType.CHAR, key.char
            # 仮想キーコードのみの場合
            return KeyType.SPECIAL, f"vk:{key.vk}"
        
        # 特殊キー（Key enum）
        if isinstance(key, keyboard.Key):
            return KeyType.SPECIAL, key.name
        
        # それ以外
        return KeyType.SPECIAL, str(key)
    
    def _update_modifier(self, key, is_press: bool) -> None:
        """修飾キーの状態を更新"""
        if key in self.MODIFIER_KEYS:
            mod_name = self.MODIFIER_KEYS[key]
            self._modifiers[mod_name] = is_press
    
    def _create_event(self, key, is_press: bool) -> KeyEvent:
        """KeyEventオブジェクトを生成"""
        key_type, key_value = self._classify_key(key)
        return KeyEvent(
            key_type=key_type,
            key_value=key_value,
            is_press=is_press,
            modifiers=self.modifiers,
        )
    
    def _on_press(self, key) -> Optional[bool]:
        """キー押下時のコールバック（内部用）"""
        # 修飾キーの状態を更新
        self._update_modifier(key, True)
        
        # イベントを生成
        event = self._create_event(key, is_press=True)
        
        # コールバック呼び出し
        if self.on_key_event:
            self.on_key_event(event)
        
        # asyncioキューへの追加
        if self._loop and self._queue:
            asyncio.run_coroutine_threadsafe(
                self._queue.put(event), 
                self._loop
            )
        
        # 停止キーのチェック
        if key == self.stop_key:
            if self._loop and self._queue:
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(None),  # 終了シグナル
                    self._loop
                )
            return False  # リスナー停止
        
        return None  # 継続
    
    def _on_release(self, key) -> Optional[bool]:
        """キー解放時のコールバック（内部用）"""
        # 修飾キーの状態を更新
        self._update_modifier(key, False)
        
        # イベントを生成
        event = self._create_event(key, is_press=False)
        
        # コールバック呼び出し
        if self.on_key_event:
            self.on_key_event(event)
        
        return None  # 継続
    
    def start(self) -> None:
        """キー監視を開始（ブロッキングモード）"""
        if self._running:
            return
        
        self._running = True
        print(f"キー入力監視を開始します... ({self.stop_key.name}キーで終了)")
        
        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        ) as listener:
            self._listener = listener
            listener.join()
        
        self._running = False
        print("キー入力監視を終了しました")
    
    def start_async(self, loop: asyncio.AbstractEventLoop, 
                    queue: asyncio.Queue) -> None:
        """キー監視を開始（非同期モード）"""
        if self._running:
            return
        
        self._loop = loop
        self._queue = queue
        self._running = True
        
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self._listener.start()
    
    def stop(self) -> None:
        """キー監視を停止"""
        if self._listener:
            self._listener.stop()
        self._running = False


def check_accessibility_permission() -> tuple[bool, str]:
    """
    macOSのアクセシビリティ権限を確認
    
    Returns:
        tuple[bool, str]: (権限あり/なし/不明, 詳細メッセージ)
        - True: 権限あり（または判定不可で動作確認推奨）
        - False: 権限なし
    """
    if sys.platform != 'darwin':
        return True, "macOS以外のプラットフォーム"
    
    # pynputの権限チェック機能を使用
    # 注意: IS_TRUSTEDはListenerインスタンス化前でも参照可能だが、
    #       OS/pynputバージョンによって正確でない場合がある
    if hasattr(keyboard.Listener, 'IS_TRUSTED'):
        is_trusted = keyboard.Listener.IS_TRUSTED
        if is_trusted:
            return True, "IS_TRUSTED=True"
        else:
            # IS_TRUSTED=Falseでも実際には動作することがある
            # （権限チェックのタイミングの問題）
            return False, "IS_TRUSTED=False (実際に動作するか確認してください)"
    
    # IS_TRUSTED属性がない場合
    return True, "IS_TRUSTED属性なし（権限チェック非対応）"


def simple_demo():
    """シンプルなデモ: 同期モード"""
    print("=" * 50)
    print("pynput キー入力監視 PoC - 同期モード")
    print("=" * 50)
    
    is_trusted, detail = check_accessibility_permission()
    print(f"\n権限チェック: {detail}")
    if not is_trusted:
        print("⚠️  権限がない可能性があります")
        print("   キー入力が検出されない場合は以下を確認してください：")
        print("   システム設定 → プライバシーとセキュリティ で")
        print("   ・アクセシビリティ → ターミナル/IDEを許可")
        print("   ・入力監視 → ターミナル/IDEを許可\n")
    
    def print_event(event: KeyEvent):
        # 押下イベントのみ表示（見やすさのため）
        if event.is_press:
            print(f"  {event}")
    
    monitor = KeyMonitor(on_key_event=print_event)
    monitor.start()


async def async_demo():
    """asyncioを使った非同期デモ"""
    print("=" * 50)
    print("pynput キー入力監視 PoC - 非同期モード")
    print("=" * 50)
    
    is_trusted, detail = check_accessibility_permission()
    print(f"\n権限チェック: {detail}")
    if not is_trusted:
        print("⚠️  権限がない可能性があります")
        print("   キー入力が検出されない場合は以下を確認してください：")
        print("   システム設定 → プライバシーとセキュリティ で")
        print("   ・アクセシビリティ → ターミナル/IDEを許可")
        print("   ・入力監視 → ターミナル/IDEを許可\n")
    
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[Optional[KeyEvent]] = asyncio.Queue()
    
    monitor = KeyMonitor(stop_key=keyboard.Key.esc)
    monitor.start_async(loop, queue)
    
    print(f"キー入力監視を開始します... (Escキーで終了)")
    print("-" * 50)
    
    key_count = 0
    
    try:
        while True:
            event = await queue.get()
            
            if event is None:  # 終了シグナル
                break
            
            # 押下イベントのみカウント・表示
            if event.is_press:
                key_count += 1
                print(f"  [{key_count:3d}] {event}")
                
                # 将来的にここでBLE送信などの非同期処理を行う
                # await ble_client.send_key(event)
    
    finally:
        monitor.stop()
        print("-" * 50)
        print(f"合計 {key_count} キー入力を検出しました")
        print("キー入力監視を終了しました")


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='pynput によるキー入力監視 PoC'
    )
    parser.add_argument(
        '--async', '-a',
        dest='use_async',
        action='store_true',
        help='非同期モードで実行'
    )
    args = parser.parse_args()
    
    try:
        if args.use_async:
            asyncio.run(async_demo())
        else:
            simple_demo()
    except KeyboardInterrupt:
        print("\n中断されました")


if __name__ == "__main__":
    main()
