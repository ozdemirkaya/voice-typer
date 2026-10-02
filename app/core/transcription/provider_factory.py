"""
app/core/transcription/provider_factory.py
============================================
Config üzerinden belirtilen STT provider'ını oluşturur.
"""

from app.services.config_manager import ConfigManager
from app.core.transcription.base_provider import BaseTranscriptionProvider
from app.core.transcription.faster_whisper_provider import FasterWhisperProvider
from app.services.logger import get_logger

logger = get_logger(__name__)

def create_provider(config_manager: ConfigManager, parent=None) -> BaseTranscriptionProvider:
    provider_name = config_manager.config.stt.engine.lower()
    
    if provider_name == "faster_whisper":
        logger.info("FasterWhisperProvider secildi.")
        return FasterWhisperProvider(config_manager, parent)
    
    # Varsayilan fallback
    logger.warning(f"Bilinmeyen STT motoru '{provider_name}'. Varsayilan (faster_whisper) kullanilacak.")
    return FasterWhisperProvider(config_manager, parent)
