"""
test_config_recovery.py
"""

import json
from pathlib import Path
from app.services.config_manager import ConfigManager

def test_recovery():
    cm = ConfigManager()
    
    # Bozuk JSON testi
    bad_json_path = cm.config_path.with_name("config_test_bad.json")
    bad_json_path.write_text("{ this is not valid json")
    
    # Temporarily override config path
    cm.config_path = bad_json_path
    cm._load() # Should not crash, should create default
    assert cm.config.stt.faster_whisper.model_size == "large-v3-turbo"
    
    # Kismi bozuk veri (yanlis type, range disi)
    partial_bad = {
        "audio": {
            "sample_rate": "16000", # String verildiginde (type uyusmazligi ama cast edilebilir)
            "channels": 5 # Range disi
        },
        "stt": {
            "faster_whisper": {
                "model_size": "small", # Gecerli
                "device": "invalid_device" # Gecersiz option
            }
        },
        "general": {
            "log_level": 123 # Yanlis type, stringe cast edilemez sekilde (aslinda edilir ama enum degil)
        }
    }
    bad_json_path.write_text(json.dumps(partial_bad))
    cm._load()
    
    # 1. Type casting calismali ("16000" -> 16000)
    assert cm.config.audio.sample_rate == 16000
    
    # 2. Range disi channels (5) -> default 1 olmali
    assert cm.config.audio.channels == 1
    
    # 3. Gecerli model_size ("small") -> "small" olarak kalmali
    assert cm.config.stt.faster_whisper.model_size == "small"
    
    # 4. Gecersiz device ("invalid_device") -> default "auto" olmali
    assert cm.config.stt.faster_whisper.device == "auto"
    
    # 5. Gecersiz enum (123) -> default "INFO" olmali
    assert cm.config.general.log_level == "INFO"
    
    print("CONFIG RECOVERY VE TYPE/RANGE CHECKING TESTLERI BASARILI!")
    
    if bad_json_path.exists():
        bad_json_path.unlink()

if __name__ == "__main__":
    test_recovery()
