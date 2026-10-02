from dataclasses import dataclass

@dataclass
class TranscriptionResult:
    """STT işlemi sonucunda döndürülen veri yapısı."""
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    processing_time_seconds: float
    model_name: str
