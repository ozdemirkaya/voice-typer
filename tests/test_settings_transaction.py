"""
test_settings_transaction.py
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal
from app.services.config_manager import ConfigManager
from app.core.app_controller import AppController
from app.core.hotkey_manager import HotkeyManager

class MockSTT(QObject):
    transcription_done = Signal(object, int)
    transcription_error = Signal(str)
    model_load_started = Signal()
    model_load_finished = Signal(bool, str)
    def __init__(self):
        super().__init__()
        self.unloaded = False
    def unload_model(self):
        self.unloaded = True

class FakeTray(QObject):
    record_requested = Signal()
    recover_requested = Signal()
    settings_requested = Signal()
    def notify(self, *args, **kwargs): pass
    def set_state(self, state): pass
    def update_record_action(self, state): pass

def test_transaction():
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = ConfigManager()
    
    hk = HotkeyManager(cfg)
    controller = AppController(cfg, FakeTray())
    controller.register_hotkey_manager(hk)
    
    stt = MockSTT()
    controller.register_stt_provider(stt)
    
    hk.setup() # Registers from config
    
    old_hotkey = hk.active_combo
    
    # 1. Simulate settings window logic
    import copy
    new_cfg = copy.deepcopy(cfg.config)
    
    # Change hotkey
    new_cfg.hotkey.key = "y"
    new_cfg.hotkey.modifiers = ["ctrl", "shift"]
    
    # Simulate runtime apply (success)
    res = hk.change_hotkey(new_cfg.hotkey.modifiers, new_cfg.hotkey.key)
    assert res == True, "Failed to apply new hotkey in runtime"
    
    assert hk.active_combo == "CTRL+SHIFT+Y"
    
    # Simulate config save FAILURE
    try:
        # Mocking an exception
        raise OSError("Disk full")
    except Exception as e:
        # Rollback
        hk.change_hotkey(cfg.config.hotkey.modifiers, cfg.config.hotkey.key)
        
    # Assert hotkey reverted
    assert hk.active_combo == old_hotkey, f"Hotkey didn't revert! It is {hk.active_combo}"
    
    # 2. Simulate model unload condition
    new_cfg2 = copy.deepcopy(cfg.config)
    new_cfg2.stt.faster_whisper.vad_filter = not new_cfg2.stt.faster_whisper.vad_filter
    
    stt_old = cfg.config.stt.faster_whisper
    stt_new = new_cfg2.stt.faster_whisper
    
    # VAD change should NOT unload
    if (stt_old.model_size != stt_new.model_size or 
        stt_old.device != stt_new.device or 
        stt_old.compute_type != stt_new.compute_type):
        stt.unload_model()
        
    assert stt.unloaded == False, "VAD change triggered unload!"
    
    # Compute type change SHOULD unload
    new_cfg2.stt.faster_whisper.compute_type = "float16"
    stt_new = new_cfg2.stt.faster_whisper
    if (stt_old.model_size != stt_new.model_size or 
        stt_old.device != stt_new.device or 
        stt_old.compute_type != stt_new.compute_type):
        stt.unload_model()
        
    assert stt.unloaded == True, "Compute change didn't trigger unload!"
    
    print("SETTINGS TRANSACTIONAL ROLLBACK VE UNLOAD SARTLARI BASARILI!")

if __name__ == "__main__":
    test_transaction()
