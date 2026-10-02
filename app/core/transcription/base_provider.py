"""
app/core/transcription/base_provider.py
=========================================
Tüm STT (Speech-to-Text) motorları için ortak arayüz.
"""

from PySide6.QtCore import QObject, Signal
from app.core.audio_recorder import RecordingResult
from app.core.transcription.models import TranscriptionResult
from app.services.config_manager import ConfigManager


class BaseTranscriptionProvider(QObject):
    """
    Uygulamanın ses tanıma işlemlerini yapacak provider'ların ortak taban sınıfı.
    PySide6 QObject'ten türer ki Qt sinyallerini kullanabilsin.
    """

    # Başarılı transcription sonucu (TranscriptionResult, op_id)
    transcription_done = Signal(object, int)
    
    # Transcription veya model yükleme hatası durumunda mesaj (error_message, op_id)
    transcription_error = Signal(str, int)
    
    # Model ilk defa yüklenmeye başladığında (Tray ve UI'ı Loading'e çekmek için)
    model_load_started = Signal()
    
    # Model yüklenmesi bittiğinde (success: bool, error_message: str)
    model_load_finished = Signal(bool, str)

    def __init__(self, config_manager: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config_manager
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        """STT modelinin belleğe yüklenip yüklenmediği."""
        return self._is_loaded

    def transcribe(self, recording: RecordingResult, op_id: int) -> None:
        """
        Asenkron olarak transcription işlemini başlatır.
        Sonuçlar transcription_done veya transcription_error sinyalleri ile dönülmelidir.
        Alt sınıflar bu metodu Worker thread üzerinden implement etmelidir.
        """
        raise NotImplementedError("Alt sınıflar transcribe() metodunu implement etmeli.")

    def shutdown(self) -> None:
        """
        Uygulama kapanırken modeli bellekten temizler ve arka plan işlerini durdurur.
        """
        pass
