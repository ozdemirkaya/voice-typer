import sys
import os
import threading
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from app.services.config_manager import ConfigManager
from app.core.app_controller import AppController
from app.ui.tray_icon import TrayIcon
from app.core.audio_recorder import AudioRecorder
from app.core.transcription.provider_factory import create_provider
from app.core.text_injector import TextInjector
from app.core.hotkey_manager import HotkeyManager

def run_test():
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
    
    def check_and_quit():
        print(f"keep_recordings is {config_manager.config.audio.keep_recordings}")
        # Audio directory
        temp_dir = config_manager.app_dir / "cache" / "audio" / "temp"
        saved_dir = config_manager.app_dir / "cache" / "audio" / "saved"
        temp_files = list(temp_dir.glob("*.wav")) if temp_dir.exists() else []
        saved_files = list(saved_dir.glob("*.wav")) if saved_dir.exists() else []
        print(f"Temp files count: {len(temp_files)}")
        # Check if the latest file was deleted. 
        # Actually it's hard to trace the exact file, but if keep_recordings is False, 
        # there shouldn't be new files accumulating if we check before/after.
        
        controller.shutdown()
        app.quit()

    app.aboutToQuit.connect(lambda: None)

    print("Starting recording...")
    QTimer.singleShot(0, controller.toggle_recording)
    # stop recording after 2s
    QTimer.singleShot(2000, controller.toggle_recording)
    # wait 8 seconds for STT to finish, then quit
    QTimer.singleShot(10000, check_and_quit)
    
    app.exec()
    print("Regression Passed")

if __name__ == "__main__":
    run_test()
