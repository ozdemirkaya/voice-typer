"""
test_stale_callback.py
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QObject, Signal
from app.core.app_controller import AppController
from app.core.state_machine import AppState
from app.services.config_manager import ConfigManager
import app.services.logger as logger_module

logger_module.setup_logging("DEBUG", None)

class MockAudioRecorder(QObject):
    recording_stopped = Signal(object, int)
    recording_failed = Signal(str)
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
    def start(self, op_id):
        self.active_op = op_id
        return True
    def stop(self):
        class RR:
            path = Path(f"fake_{self.active_op}.wav")
            duration_seconds = 2.0
            is_valid = True
            def exists(self): return False
        self.recording_stopped.emit(RR(), self.active_op)

class MockSTTProvider(QObject):
    transcription_done = Signal(object, int)
    transcription_error = Signal(str)
    model_load_started = Signal()
    model_load_finished = Signal(bool, str)
    def transcribe(self, result, op_id):
        # Do nothing immediately. We will trigger it manually.
        pass
    def shutdown(self): pass

class MockTextInjector(QObject):
    injection_done = Signal(bool, str)
    def __init__(self):
        super().__init__()
        self.injected_texts = []
    def inject(self, text, hwnd):
        self.injected_texts.append(text)

class FakeTray(QObject):
    record_requested = Signal()
    recover_requested = Signal()
    settings_requested = Signal()
    def notify(self, *args, **kwargs): pass
    def set_state(self, state): pass
    def update_record_action(self, state): pass

def test_stale():
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = ConfigManager()
    cfg.config.audio.keep_recordings = False
    
    controller = AppController(cfg, FakeTray())
    controller.register_audio_recorder(MockAudioRecorder(cfg))
    stt = MockSTTProvider()
    controller.register_stt_provider(stt)
    injector = MockTextInjector()
    controller.register_text_injector(injector)
    
    # 1. Start Operation 1
    controller.toggle_recording() # op_id = 1
    controller.toggle_recording() # stops, goes to processing
    
    assert controller.state == AppState.PROCESSING
    
    # Simulate an error to push state to ERROR
    controller.error_occurred.emit("Fake Error to test recovery")
    assert controller.state == AppState.ERROR
    
    controller.recover_from_error() # goes to IDLE
    assert controller.state == AppState.IDLE
    
    # 2. Start Operation 2
    controller.toggle_recording() # op_id = 2, recording
    assert controller.state == AppState.RECORDING
    
    # 3. NOW, delayed STT callback for Operation 1 arrives!
    class TR:
        text = "Delayed Text from Op 1"
        processing_time_seconds = 1.0
    stt.transcription_done.emit(TR(), 1)
    
    # 4. State must STILL be RECORDING. Text must NOT be injected!
    assert controller.state == AppState.RECORDING, f"State is {controller.state}"
    assert len(injector.injected_texts) == 0, "Stale text was injected!"
    
    print("\nSTALE CALLBACK PROTECTED SUCCESSFULLY!")
    
    QTimer.singleShot(100, app.quit)
    app.exec()

if __name__ == "__main__":
    test_stale()
