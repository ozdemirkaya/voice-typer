"""
app/core/exceptions.py
=======================
Uygulama genelinde kullanilan merkezi hata siniflari.
"""

class VoiceTyperError(Exception):
    """Voice Typer taban hata sinifi."""
    pass

class AudioError(VoiceTyperError):
    """Ses kayit donanimi ve stream isleme hatalari."""
    pass

class STTError(VoiceTyperError):
    """Ses tanima islemi sirasinda olusan hatalar."""
    pass

class ModelLoadError(STTError):
    """Yapay zeka modelinin yuklenmesi ve baslatilmasi sirasinda olusan hatalar."""
    pass

class HotkeyError(VoiceTyperError):
    """Global klavye kisayol kaydi sirasinda olusan hatalar."""
    pass

class ClipboardError(VoiceTyperError):
    """Windows pano islemleri sirasinda olusan hatalar."""
    pass

class TextInjectionError(VoiceTyperError):
    """Metnin hedef pencereye yazilmasi sirasinda olusan hatalar."""
    pass

class ConfigError(VoiceTyperError):
    """Ayar dosyasinin okunmasi veya bozulmasiyla ilgili hatalar."""
    pass
