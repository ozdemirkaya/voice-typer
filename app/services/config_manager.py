"""
app/services/config_manager.py
================================
Uygulama yapılandırmasını yöneten modül.

Özellikler:
- Tüm ayarlar güçlü tipli Python dataclass'larında tutulur.
- config.json'dan yüklenir; eksik anahtarlar varsayılan değerlerle doldurulur.
- Yeni config anahtarları eklendiğinde mevcut kullanıcı dosyaları otomatik güncellenir.
- Thread-safe: RLock ile korunur.
- Atomik yazma: geçici dosya → rename (yarım yazma riski yok).

Kullanım:
    from app.services.config_manager import ConfigManager

    cfg = ConfigManager()
    print(cfg.config.stt.faster_whisper.model_size)

    cfg.config.general.log_level = "DEBUG"
    cfg.save()
"""

import json
import sys
import threading
from app.core.exceptions import ConfigError
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Uygulama dizini tespiti
# ---------------------------------------------------------------------------

def _get_app_dir() -> Path:
    """
    Kullanıcı verilerinin (config, logs, vb.) saklanacağı dizini döndürür.
    - PyInstaller ile paketlenmişse: %LOCALAPPDATA%\VoiceTyper
    - Kaynak koddan çalıştırılıyorsa: Proje kök dizini (Development mode)
    """
    if getattr(sys, "frozen", False):
        import os
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "VoiceTyper"
        return Path(sys.executable).parent / "UserData"
    
    # Kaynak modu: app/services/config_manager.py → ../../ = proje kökü
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Config Dataclass'ları
# ---------------------------------------------------------------------------

@dataclass
class HotkeyConfig:
    """Global kısayol tuşu ayarları."""
    # Kullanılabilir modifier'lar: "alt", "ctrl", "shift", "win"
    modifiers: list = field(default_factory=lambda: ["alt"])
    # Tek karakter veya sanal tuş adı, örn. "x", "f1"
    key: str = "x"


@dataclass
class AudioConfig:
    """Mikrofon ve ses kaydı ayarları."""
    # None = sistem varsayılan mikrofonu
    device_index: Optional[int] = None
    # Kayıt edilecek örnekleme hızı (0 ise cihazın native hızı kullanılır)
    sample_rate: int = 0
    channels: int = 1
    # Bu süreden kısa kayıtlar (örn. kazara tuşa basıp bırakma) iptal edilir.
    min_duration_ms: int = 500
    # Başarılı transcription sonrasında WAV dosyasının silinip silinmeyeceği
    # Güvenlik ve disk alanı için varsayılan: False
    keep_recordings: bool = False



@dataclass
class VADParameters:
    """
    faster-whisper built-in Silero VAD parametreleri.

    MVP'de faster-whisper varsayılan değerleri kullanılır.
    İleride Settings ekranından özelleştirilebilir.
    """
    # Konuşma tespit eşiği (0.0–1.0). Düşük = daha hassas ama gürültüye açık.
    threshold: float = 0.5
    # Bu süreden kısa konuşma parçaları atılır (ms).
    min_speech_duration_ms: int = 250
    # Konuşma bittikten sonra bu kadar sessizlik beklenir (ms).
    min_silence_duration_ms: int = 2000
    # Konuşma bölgelerinin başına/sonuna eklenen dolgu (ms).
    speech_pad_ms: int = 400


@dataclass
class FasterWhisperConfig:
    """faster-whisper model ve transcription ayarları."""

    # Kullanılabilir: tiny, base, small, medium, large-v2, large-v3, large-v3-turbo
    model_size: str = "large-v3-turbo"

    # "auto"  → CUDA mevcutsa GPU, yoksa CPU
    # "cpu"   → Her zaman CPU
    # "cuda"  → Her zaman GPU (CUDA yoksa hata)
    device: str = "auto"

    # "auto"  → GPU'da float16, CPU'da int8
    # "int8"  → Tüm platformlarda int8 (düşük RAM, az hız kaybı)
    # "float16" → GPU'da yüksek hız
    # "float32" → CPU'da yüksek doğruluk, yüksek RAM
    compute_type: str = "auto"

    # VAD (Voice Activity Detection) filtresi aktif olsun mu?
    vad_filter: bool = True

    # faster-whisper dil kodu: "tr" = Türkçe
    language: str = "tr"

    # VAD filtresi aktif mi?
    vad_enabled: bool = True

    # VAD parametreleri (boş dict → faster-whisper varsayılanları)
    vad_parameters: VADParameters = field(default_factory=VADParameters)


@dataclass
class STTConfig:
    """Speech-to-Text engine seçimi ve ayarları."""
    # MVP: sadece "faster_whisper"
    # İleride: "groq", "openai" vb. eklenebilir
    engine: str = "faster_whisper"
    faster_whisper: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)


@dataclass
class TextInjectionConfig:
    """Aktif pencereye metin yazma ayarları."""
    # Ctrl+V gönderildikten sonra clipboard restore öncesi bekleme süresi (ms).
    # Bazı uygulamalar clipboard verisini gecikmeli okur (örn. Electron tabanlı).
    # Sabit sayı değil — config'den yönetilir.
    paste_delay_ms: int = 250


@dataclass
class GeneralConfig:
    """Genel uygulama ayarları."""
    # Windows başlangıcında otomatik çalıştır (Registry)
    run_on_startup: bool = False
    # Dosyaya yazılacak log seviyesi: "DEBUG" | "INFO" | "WARNING" | "ERROR"
    log_level: str = "INFO"


@dataclass
class AppConfig:
    """Uygulamanın tam yapılandırması."""
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    text_injection: TextInjectionConfig = field(default_factory=TextInjectionConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """
    `override` dict'ini `base` dict'ine derinlemesine birleştirir.

    - `override`'da olmayan `base` anahtarları korunur (yeni config key'leri için).
    - `override`'da olan değerler `base`'deki değerlerin üzerine yazar.
    - Her iki tarafta da dict olan değerler özyinelemeli birleştirilir.
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _nested_get(data: dict, *keys: str, default: Any = None, expected_type: type = None, valid_range: tuple = None, valid_options: list = None) -> Any:
    """
    İç içe dict'ten güvenli değer okuyucu. (Phase 8: Robust Type & Range Checking)
    Örnek: _nested_get(d, "stt", "faster_whisper", "model_size", default="small", expected_type=str)
    """
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
            
    # Type kontrolü
    if expected_type is not None and current is not None:
        if not isinstance(current, expected_type):
            try:
                # Eger int bekliyorsak ve float geldiyse vb. type casting yapmayi dene
                current = expected_type(current)
            except (ValueError, TypeError):
                print(f"[ConfigManager] Type uyusmazligi! Beklenen: {expected_type.__name__}, Gelen: {type(current).__name__} (Key: {keys})")
                return default
                
    # Range kontrolü (sayisal degerler icin)
    if valid_range is not None and current is not None:
        min_val, max_val = valid_range
        if not (min_val <= current <= max_val):
            print(f"[ConfigManager] Deger sinirlar disinda! Gelen: {current}, Sinirlar: {valid_range} (Key: {keys})")
            return default
            
    # Option kontrolü (enum benzeri string degerler icin)
    if valid_options is not None and current is not None:
        if current not in valid_options:
            print(f"[ConfigManager] Gecersiz secenek! Gelen: {current}, Gecerli: {valid_options} (Key: {keys})")
            return default
            
    return current


def _build_config(data: dict) -> AppConfig:
    """
    Düz dict'ten güçlü tipli AppConfig oluşturur.
    Her alan için açık default değerler tanımlıdır — eksik key güvenli.
    """
    g = _nested_get  # Kısa alias

    return AppConfig(
        hotkey=HotkeyConfig(
            modifiers=g(data, "hotkey", "modifiers", default=["alt"], expected_type=list),
            key=g(data, "hotkey", "key", default="x", expected_type=str),
        ),
        audio=AudioConfig(
            device_index=g(data, "audio", "device_index", default=None, expected_type=int),
            sample_rate=g(data, "audio", "sample_rate", default=16000, expected_type=int, valid_range=(0, 192000)),
            channels=g(data, "audio", "channels", default=1, expected_type=int, valid_range=(1, 2)),
        ),
        stt=STTConfig(
            engine=g(data, "stt", "engine", default="faster_whisper", expected_type=str, valid_options=["faster_whisper"]),
            faster_whisper=FasterWhisperConfig(
                model_size=g(data, "stt", "faster_whisper", "model_size", default="large-v3-turbo", expected_type=str),
                device=g(data, "stt", "faster_whisper", "device", default="auto", expected_type=str, valid_options=["auto", "cpu", "cuda"]),
                compute_type=g(data, "stt", "faster_whisper", "compute_type", default="auto", expected_type=str, valid_options=["auto", "int8", "float16", "float32"]),
                language=g(data, "stt", "faster_whisper", "language", default="tr", expected_type=str),
                vad_enabled=g(data, "stt", "faster_whisper", "vad_enabled", default=True, expected_type=bool),
                vad_parameters=VADParameters(
                    threshold=g(data, "stt", "faster_whisper", "vad_parameters", "threshold", default=0.5, expected_type=float, valid_range=(0.0, 1.0)),
                    min_speech_duration_ms=g(data, "stt", "faster_whisper", "vad_parameters", "min_speech_duration_ms", default=250, expected_type=int, valid_range=(0, 2000)),
                    min_silence_duration_ms=g(data, "stt", "faster_whisper", "vad_parameters", "min_silence_duration_ms", default=2000, expected_type=int, valid_range=(0, 10000)),
                    speech_pad_ms=g(data, "stt", "faster_whisper", "vad_parameters", "speech_pad_ms", default=400, expected_type=int, valid_range=(0, 2000)),
                ),
            ),
        ),
        text_injection=TextInjectionConfig(
            paste_delay_ms=g(data, "text_injection", "paste_delay_ms", default=250, expected_type=int, valid_range=(0, 2000)),
        ),
        general=GeneralConfig(
            run_on_startup=g(data, "general", "run_on_startup", default=False, expected_type=bool),
            log_level=g(data, "general", "log_level", default="INFO", expected_type=str, valid_options=["DEBUG", "INFO", "WARNING", "ERROR"]),
        ),
    )


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """
    Thread-safe uygulama yapılandırma yöneticisi.

    Örnek kullanım:
        cfg = ConfigManager()
        model = cfg.config.stt.faster_whisper.model_size
        cfg.config.general.log_level = "DEBUG"
        cfg.save()
    """

    CONFIG_FILENAME = "config.json"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.app_dir: Path = _get_app_dir()
        self.config_path: Path = self.app_dir / self.CONFIG_FILENAME
        self._config: AppConfig = AppConfig()  # Başlangıç varsayılanları
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        """Mevcut uygulama yapılandırmasını döndürür (thread-safe)."""
        with self._lock:
            return self._config

    def save(self) -> bool:
        """
        Mevcut yapılandırmayı diske yazar.

        Atomik yazma: önce .tmp dosyasına, sonra rename ile yerleştir.
        Returns:
            True  → başarılı
            False → yazma hatası (loglara bakın)
        """
        with self._lock:
            data = asdict(self._config)
            try:
                self.app_dir.mkdir(parents=True, exist_ok=True)
                tmp_path = self.config_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                    fh.flush()
                    import os
                    os.fsync(fh.fileno())
                import os
                os.replace(tmp_path, self.config_path)
                return True
            except OSError as exc:
                # Logger henüz hazır olmayabilir (çok erken çağrı), print kullan.
                print(f"[ConfigManager] Config kaydedilemedi: {exc}")
                return False

    def reload(self) -> None:
        """Config dosyasını diskten yeniden yükler (runtime güncelleme için)."""
        with self._lock:
            self._load()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """
        Config dosyasını diskten okur ve varsayılanlarla birleştirir.

        - Dosya yoksa → varsayılan config oluşturulur ve diske yazılır.
        - Dosya bozuksa → varsayılan config kullanılır, eski dosyanın üzerine yazılır.
        - Dosya eskiyse (yeni key'ler eksik) → deep_merge ile tamamlanır.
        """
        defaults = asdict(AppConfig())

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    user_data = json.load(fh)

                if not isinstance(user_data, dict):
                    err = ConfigError("Config dosyası geçerli bir JSON objesi değil.")
                    raise err

                merged = _deep_merge(defaults, user_data)
                print(f"[ConfigManager] Config yüklendi: {self.config_path}")

            except (json.JSONDecodeError, ConfigError, OSError) as exc:
                print(f"[ConfigManager] Config okunamadı ({exc}), varsayılanlar kullanılıyor.")
                
                # Exception chaining (Phase 8 verification)
                cfg_err = ConfigError(f"Config yuklenirken hata: {exc}")
                cfg_err.__cause__ = exc
                
                # Bozuk dosyayi yedekle (Phase 8)
                import time
                import shutil
                try:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    backup_path = self.config_path.with_name(f"config.corrupt-{timestamp}.json")
                    shutil.copy2(self.config_path, backup_path)
                    print(f"[ConfigManager] Bozuk config yedeklendi: {backup_path.name}")
                except Exception as b_exc:
                    print(f"[ConfigManager] Bozuk config yedeklenemedi: {b_exc}")
                    
                merged = defaults
        else:
            print(f"[ConfigManager] Config bulunamadı, varsayılan oluşturuluyor: {self.config_path}")
            merged = defaults

        self._config = _build_config(merged)

        # Her yüklemede kaydet — yeni key'leri ve değişikliği diske yansıt.
        self.save()
