"""
Test Script to Verify State Machine Transitions
"""
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QObject, Signal
from app.core.app_controller import AppController
from app.core.state_machine import AppState
from app.services.config_manager import ConfigManager
import app.services.logger as logger_module

logger_module.setup_logging("DEBUG", None)
logger = logger_module.get_logger(__name__)

class MockAudioRecorder(QObject):
    recording_stopped = Signal(object, int)
    recording_failed = Signal(str, int)
    def __init__(self):
        super().__init__()
        self.active_op = None
    def start(self, op_id: int):
        self.active_op = op_id
        return True
    def stop(self):
        class RR:
            path = Path("fake.wav")
            duration_seconds = 2.0
            is_valid = True
            def exists(self): return False
            def unlink(self): pass
        self.recording_stopped.emit(RR(), self.active_op)

class MockSTTProvider(QObject):
    transcription_done = Signal(object, int)
    transcription_error = Signal(str, int)
    model_load_started = Signal()
    model_load_finished = Signal(bool, str)
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
    def transcribe(self, result, op_id):
        pass

class MockTextInjector(QObject):
    injection_done = Signal(bool, str)
    def inject(self, text, hwnd):
        logger.info("text injection completed")

class MockRecordingResult:
    def __init__(self):
        self.is_valid = True
        self.duration_seconds = 2.0
        self.path = Path("fake.wav")
    def exists(self): return False

class MockTranscriptionResult:
    def __init__(self):
        self.text = "Deneme"
        self.processing_time_seconds = 1.0

def test_state_transitions():
    app = QApplication.instance() or QApplication(sys.argv)
    config = ConfigManager()
    
    class FakeTray(QObject):
        record_requested = Signal()
        recover_requested = Signal()
        settings_requested = Signal()
        def notify(self, *args, **kwargs): pass
        def set_state(self, state): pass
    
    controller = AppController(config, FakeTray())
    
    recorder = MockAudioRecorder()
    controller.register_audio_recorder(recorder)
    stt = MockSTTProvider(controller)
    controller.register_stt_provider(stt)
    controller.register_text_injector(MockTextInjector())
    
    print("\n--- SIMULATING USER WORKFLOW ---")
    
    print("\n[User triggers recording]")
    controller.toggle_recording()
    
    op_id = controller._current_op.operation_id
    
    print("\n[User stops recording]")
    controller.toggle_recording()
    
    print("\n[STT provider starts loading model]")
    controller.on_model_load_started()
    
    print("\n[STT provider finishes loading model]")
    controller.on_model_load_finished(True)
    
    print("\n[STT provider finishes transcription]")
    controller.on_transcription_done(MockTranscriptionResult(), op_id)
    
    print("\n--- TEST FINISHED ---")
    QTimer.singleShot(100, app.quit)
    app.exec()

if __name__ == "__main__":
    test_state_transitions()
