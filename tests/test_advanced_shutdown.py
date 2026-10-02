import sys
import os
import threading
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.services.config_manager import ConfigManager
from app.core.app_controller import AppController
from app.ui.tray_icon import TrayIcon
from app.core.audio_recorder import AudioRecorder
from app.core.transcription.provider_factory import create_provider
from app.core.text_injector import TextInjector
from app.core.hotkey_manager import HotkeyManager

def run_test(scenario):
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config_manager = ConfigManager()
    tray = TrayIcon(config_manager=config_manager)
    
    controller = AppController(config_manager=config_manager, tray_icon=tray)
    
    audio_recorder = AudioRecorder(config_manager=config_manager)
    controller.register_audio_recorder(audio_recorder)
    
    stt_provider = create_provider(config_manager, parent=controller)
    controller.register_stt_provider(stt_provider)
    
    text_injector = TextInjector(config_manager=config_manager, parent=controller)
    controller.register_text_injector(text_injector)
    
    hotkey_manager = HotkeyManager(config_manager=config_manager)
    controller.register_hotkey_manager(hotkey_manager)
    
    def _on_quit():
        controller.shutdown()
    
    app.aboutToQuit.connect(_on_quit)

    if scenario == "RECORDING":
        QTimer.singleShot(500, controller.toggle_recording)
    elif scenario == "PROCESSING":
        QTimer.singleShot(500, controller.toggle_recording)
        # stop after 1s to trigger processing
        QTimer.singleShot(1500, controller.toggle_recording)

    def force_quit():
        print(f"[{scenario}] Triggering exit...")
        tray._on_quit()

    QTimer.singleShot(3000, force_quit)
    
    ret = app.exec()
    print(f"[{scenario}] Process gracefully exiting with code {ret}")
    # Don't sys.exit here, let it return so we can run multiple tests
    # We must disconnect the signal to avoid calling it again in next test
    app.aboutToQuit.disconnect(_on_quit)
    
    # We must manually clear references or it might crash Qt
    controller.deleteLater()
    tray.deleteLater()

if __name__ == "__main__":
    print("=== TEST 2: RECORDING ===")
    run_test("RECORDING")
    
    print("\n=== TEST 3: PROCESSING ===")
    run_test("PROCESSING")
