"""
main.py — Voice Typer Giriş Noktası
=====================================
Uygulama bu dosyadan başlatılır.

Sorumluluklar:
1. Tek örnek (single instance) kontrolü — Windows named mutex.
2. QApplication oluşturma ve yapılandırma.
3. ConfigManager başlatma.
4. Loglama altyapısını kurma.
5. Sistem tray ikonunu gösterme.
6. Qt event loop başlatma.
7. Temiz kapatma.
"""

import sys
import os
import ctypes
from pathlib import Path

# ---------------------------------------------------------------------------
# Proje kökünü sys.path'e ekle (kaynak moddan çalıştırma için)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import app.services.startup_manager  # PyInstaller dependency resolving için top-level import


# ---------------------------------------------------------------------------
# Qt importları
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

# ---------------------------------------------------------------------------
# Uygulama sabitleri
# ---------------------------------------------------------------------------
APP_NAME = "VoiceTyper"
APP_DISPLAY_NAME = "Voice Typer"
APP_VERSION = "0.1.0"

# Windows named mutex — çakışma riskini minimuma indirmek için Global\ prefix
_MUTEX_NAME = f"Global\\{APP_NAME}SingleInstanceMutex"


# ---------------------------------------------------------------------------
# Tek örnek kontrolü
# ---------------------------------------------------------------------------

# Mutex handle'ı process boyunca canlı tutmak için modül seviyesinde sakla.
# GC tarafından erken temizlenmemesi kritik.
_mutex_handle = None


def _acquire_single_instance_mutex() -> bool:
    """
    Windows named mutex ile tek örnek garantisi.

    Returns:
        True  → Bu ilk/tek örnek, devam et.
        False → Başka bir örnek zaten çalışıyor.
    """
    global _mutex_handle

    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()

    ERROR_ALREADY_EXISTS = 183

    if last_error == ERROR_ALREADY_EXISTS:
        # Mutex zaten vardı — başka bir örnek çalışıyor
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        return False

    # Mutex başarıyla oluşturuldu — handle'ı sakla
    _mutex_handle = handle
    return True


def _release_single_instance_mutex() -> None:
    """Uygulama kapanırken mutex'i serbest bırak."""
    global _mutex_handle
    if _mutex_handle:
        ctypes.windll.kernel32.ReleaseMutex(_mutex_handle)
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Uygulama giriş noktası.

    Returns:
        int: Çıkış kodu (0 = başarılı).
    """

    # Windows'ta yüksek DPI monitör desteği
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    # QApplication — tüm Qt widget'larından önce oluşturulmalı
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("VoiceTyper")

    # Tray uygulaması: son pencere kapanınca çıkma
    app.setQuitOnLastWindowClosed(False)

    # ----------------------------------------------------------------
    # Tek örnek kontrolü
    # ----------------------------------------------------------------
    if not _acquire_single_instance_mutex():
        QMessageBox.information(
            None,
            APP_DISPLAY_NAME,
            "Voice Typer zaten çalışıyor.\n\n"
            "Görev çubuğu bildirim alanını (system tray) kontrol edin.",
        )
        return 0

    # ----------------------------------------------------------------
    # Config
    # ----------------------------------------------------------------
    from app.services.config_manager import ConfigManager
    config_manager = ConfigManager()

    # ----------------------------------------------------------------
    # Startup (Run on Boot) sync
    # ----------------------------------------------------------------
    from app.services import startup_manager
    startup_manager.sync_with_config(config_manager.config.general.run_on_startup)

    # ----------------------------------------------------------------
    # Loglama — config'den log seviyesi alındıktan sonra başlat
    # ----------------------------------------------------------------
    from app.services.logger import setup_logging, get_logger

    setup_logging(
        log_level=config_manager.config.general.log_level,
        log_dir=config_manager.app_dir / "logs",
    )
    logger = get_logger(__name__)

    logger.info("=" * 64)
    logger.info(f"{APP_DISPLAY_NAME} v{APP_VERSION} başlatılıyor")
    logger.info(f"Python sürümü : {sys.version.split()[0]}")
    
    is_frozen = getattr(sys, "frozen", False)
    logger.info(f"frozen = {is_frozen}")
    logger.info(f"sys.executable = {sys.executable}")
    
    # Bundle internal path calculation for logs
    resource_root = sys._MEIPASS if hasattr(sys, "_MEIPASS") else str(Path(sys.executable).parent / "_internal") if is_frozen else str(_PROJECT_ROOT)
    logger.info(f"resource root = {resource_root}")
    logger.info(f"user-data root = {config_manager.app_dir}")
    
    model_cache_root = config_manager.app_dir / "models"
    logger.info(f"model cache root = {model_cache_root}")
    
    cuda_source = str(Path(resource_root) / "cuda_runtime") if is_frozen else "venv"
    logger.info(f"CUDA runtime source = {cuda_source}")

    logger.info(f"Config dosyası : {config_manager.config_path}")
    logger.info(f"Log seviyesi   : {config_manager.config.general.log_level}")
    
    cfg_stt = config_manager.config.stt.faster_whisper
    logger.info(f"STT motoru     : {config_manager.config.stt.engine}")
    logger.info(f"configured model = {cfg_stt.model_size}")
    logger.info(f"configured device = {cfg_stt.device}")
    logger.info(f"configured compute_type = {cfg_stt.compute_type}")
    
    try:
        from app.core.runtime_profile_resolver import RuntimeProfileResolver
        res_model, res_device, res_comp = RuntimeProfileResolver.resolve_profile(config_manager)
        logger.info(f"resolved model = {res_model}")
        logger.info(f"resolved device = {res_device}")
        logger.info(f"resolved compute_type = {res_comp}")
    except Exception as e:
        logger.warning(f"resolve_profile basarisiz: {e}")


    # ----------------------------------------------------------------
    # Sistem tray ikonu
    # ----------------------------------------------------------------
    if not QSystemTrayIcon_is_available():
        logger.error("Sistem çubuğu (system tray) bu ortamda desteklenmiyor.")
        QMessageBox.critical(
            None,
            APP_DISPLAY_NAME,
            "Bu sistem sistem çubuğunu (system tray) desteklemiyor.\n"
            "Uygulama kapatılıyor.",
        )
        _release_single_instance_mutex()
        return 1

    from app.ui.tray_icon import TrayIcon
    tray = TrayIcon(config_manager=config_manager)
    tray.show()

    # ----------------------------------------------------------------
    # AppController — merkezi koordinasyon katmanı
    # ----------------------------------------------------------------
    from app.core.app_controller import AppController
    controller = AppController(
        config_manager=config_manager,
        tray_icon=tray,
    )

    # TrayIcon sinyallerini controller'a bağla
    tray.record_requested.connect(controller.toggle_recording)
    tray.recover_requested.connect(controller.recover_from_error)
    
    def show_settings():
        from app.ui.settings_window import SettingsWindow
        SettingsWindow.show_window(config_manager, controller, parent=None)
        
    tray.settings_requested.connect(show_settings)


    # ----------------------------------------------------------------
    # AudioRecorder — Phase 4: Ses Kaydı
    # ----------------------------------------------------------------
    from app.core.audio_recorder import AudioRecorder
    audio_recorder = AudioRecorder(config_manager=config_manager)
    controller.register_audio_recorder(audio_recorder)

    # ----------------------------------------------------------------
    # STT Provider — Phase 5: Ses Tanıma
    # ----------------------------------------------------------------
    from app.core.transcription.provider_factory import create_provider
    stt_provider = create_provider(config_manager, parent=controller)
    controller.register_stt_provider(stt_provider)

    # ----------------------------------------------------------------
    # TextInjector — Phase 6: Metin Yazma
    # ----------------------------------------------------------------
    from app.core.text_injector import TextInjector
    text_injector = TextInjector(config_manager=config_manager, parent=controller)
    controller.register_text_injector(text_injector)

    # ----------------------------------------------------------------
    # HotkeyManager — Phase 3: Global kısayol
    # ----------------------------------------------------------------

    from app.core.hotkey_manager import HotkeyManager
    hotkey_manager = HotkeyManager(config_manager=config_manager)
    controller.register_hotkey_manager(hotkey_manager)


    # setup(): native event filter'ı kur + config'deki kısayolu register et.
    # Başarısız olursa tray bildirimi gösterilir, uygulama çalışmaya devam eder.
    hotkey_setup_ok = hotkey_manager.setup()

    # ----------------------------------------------------------------
    # Kapatma işleyicisi
    # ----------------------------------------------------------------
    def _on_quit() -> None:
        logger.info("Uygulama kapatılıyor...")
        controller.shutdown()
        _release_single_instance_mutex()
        logger.info("Temiz kapatma tamamlandı.")

    app.aboutToQuit.connect(_on_quit)

    # ----------------------------------------------------------------
    # Başarılı başlangıç bildirimi
    # ----------------------------------------------------------------
    logger.info("Uygulama başarıyla başlatıldı. Sistem çubuğunda çalışıyor.")
    if hotkey_setup_ok:
        logger.info(f"Kısayol aktif: {hotkey_manager.active_combo}")
    else:
        logger.warning("Kısayol register edilemedi — tray menüsü üzerinden kullanılabilir.")

    return app.exec()



def QSystemTrayIcon_is_available() -> bool:
    """Sistem tray'in bu platformda kullanılabilir olup olmadığını kontrol eder."""
    from PySide6.QtWidgets import QSystemTrayIcon
    return QSystemTrayIcon.isSystemTrayAvailable()


# ---------------------------------------------------------------------------
# Global hata yakalama
# ---------------------------------------------------------------------------

def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """
    Yakalanmamış istisnaları loglar.
    Qt thread'lerinde patlayan hatalar burada son şansı yakalar.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    try:
        from app.services.logger import get_logger as _get_logger
        _logger = _get_logger("uncaught")
        _logger.critical(
            "Yakalanmamış istisna!",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
    except Exception:
        # Logger da başarısız olursa standart stderr'e yaz
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback)


sys.excepthook = _handle_uncaught_exception


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
