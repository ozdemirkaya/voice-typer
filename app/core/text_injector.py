"""
app/core/text_injector.py
===========================
STT'den gelen metni hedef pencereye yapistiran modul.
"""

import ctypes
import time
import win32gui
from ctypes import wintypes
from PySide6.QtCore import QObject, Signal

from app.services.config_manager import ConfigManager
from app.core.clipboard_manager import ClipboardManager
from app.services.logger import get_logger
from app.core.exceptions import TextInjectionError

logger = get_logger(__name__)

# --- Win32 SendInput Structures ---
user32 = ctypes.WinDLL('user32', use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)))

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),
                    ("mi", ctypes.c_int * 7),
                    ("hi", ctypes.c_int * 4))
    _anonymous_ = ("_input",)
    _fields_ = (("type", wintypes.DWORD),
                ("_input", _INPUT))

def _send_input(vk, down=True):
    """Belirtilen sanal tusu gonderir."""
    extra = ctypes.c_ulong(0)
    ii_ = INPUT._INPUT()
    flags = 0 if down else KEYEVENTF_KEYUP
    ii_.ki = KEYBDINPUT(vk, 0, flags, 0, ctypes.pointer(extra))
    x = INPUT(type=INPUT_KEYBOARD, _input=ii_)
    user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

def _send_ctrl_v():
    """Ctrl+V tus kombinasyonunu gonderir."""
    try:
        _send_input(VK_CONTROL, down=True)
        time.sleep(0.01)
        _send_input(VK_V, down=True)
        time.sleep(0.01)
        _send_input(VK_V, down=False)
    finally:
        # Hata olsa bile Ctrl basili kalmasin
        _send_input(VK_CONTROL, down=False)

class TextInjector(QObject):
    """
    Transcription tamamlandiginda metni panoya yazar ve hedef uygulamaya Ctrl+V yollar.
    """
    
    # Islem sonucu (success: bool, message: str)
    injection_done = Signal(bool, str)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config_manager
        self._clipboard = ClipboardManager()

    def inject(self, text: str, target_hwnd: int) -> None:
        """
        Gelen metni hedef pencereye yapistirir.
        Eger hedef pencere focus kaybetmisse sadece panoda birakir.
        Bos metinler icin islem yapmaz.
        """
        if not text:
            self.injection_done.emit(False, "Boş metin")
            return

        # Pencere hala var mi?
        if target_hwnd and not win32gui.IsWindow(target_hwnd):
            logger.warning("Hedef pencere kapanmis. Metin sadece panoya kopyalaniyor.")
            self._clipboard.set_text(text)
            self.injection_done.emit(False, "Pencere kapandığı için metin panoya kopyalandı.")
            return

        # Pencere hala odakta mi? (Kullanici baska yere gectiyse zorla calmamali)
        current_hwnd = win32gui.GetForegroundWindow()
        if target_hwnd and current_hwnd != target_hwnd:
            logger.warning("Focus kaybolmus. Metin sadece panoya kopyalaniyor.")
            self._clipboard.set_text(text)
            self.injection_done.emit(False, "Odak değiştiği için metin panoya kopyalandı.")
            return
            
        logger.debug(f"Pano yedekleniyor ve '{text[:30]}...' gonderiliyor.")
        
        # 1. Panoyu yedekle
        self._clipboard.backup()
        
        try:
            # 2. Metni panoya kopyala
            if not self._clipboard.set_text(text):
                self.injection_done.emit(False, "Panoya erişilemedi.")
                return
                
            # 3. Ctrl+V gonder
            _send_ctrl_v()
            
            # 4. Uygulamanin yapistirma islemini okumasi icin bekle (Electron uygulamalari vs)
            delay_sec = self._config.config.text_injection.paste_delay_ms / 1000.0
            time.sleep(delay_sec)
        except Exception as e:
            err = TextInjectionError(f"Yapistirma esnasinda hata: {e}")
            try:
                raise err from e
            except TextInjectionError as raised_err:
                logger.error("Text injection basarisiz oldu", exc_info=raised_err)
            self.injection_done.emit(False, str(err))
            return
        finally:
            # 5. Panoyu geri yukle
            self._clipboard.restore()
        
        logger.info("Metin basariyla yapistirildi ve pano geri yuklendi.")
        self.injection_done.emit(True, "Metin başarıyla yazıldı.")
