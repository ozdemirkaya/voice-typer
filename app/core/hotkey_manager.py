"""
app/core/hotkey_manager.py
===========================
Windows RegisterHotKey tabanlı global kısayol yöneticisi.

Sorumluluklar:
- Windows RegisterHotKey API ile sistem genelinde kısayol kaydı.
- WM_HOTKEY mesajlarını Qt event loop'undan önce yakalamak (QAbstractNativeEventFilter).
- Kayıt başarısız olduğunda kullanıcı dostu hata bildirimi.
- Kısayol değiştirme + rollback mekanizması.
- Uygulama kapanırken UnregisterHotKey garantisi.

AppController Windows API detaylarını bilmez:
    hotkey_pressed sinyali tetiklenince toggle_recording() çağrılır,
    RegisterHotKey / WM_HOTKEY süreci burada kapsüllenir.

Thread güvenliği:
    RegisterHotKey ve QAbstractNativeEventFilter.nativeEventFilter
    her ikisi de Qt'nin ana thread'inde çağrılır — ekstra kilitleme gerekmez.

GC koruması:
    _HotkeyNativeFilter nesnesi HotkeyManager'ın instance değişkeni olarak
    tutulur. QApplication'a referans yetmez; Python tarafında da canlı kalması
    şarttır, aksi takdirde nativeEventFilter çöper belleğe erişir.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

from app.services.config_manager import ConfigManager
from app.services.logger import get_logger
from app.core.exceptions import HotkeyError

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Windows API sabitleri
# ---------------------------------------------------------------------------

_WM_HOTKEY: int = 0x0312

# MOD_NOREPEAT: Tuş basılı tutulduğunda WM_HOTKEY sürekli gönderilmez.
# Tek fiziksel basış → tek event. Windows 8+ destekler.
_MOD_NOREPEAT: int = 0x4000

# Windows hata kodu: Kısayol zaten başka uygulama tarafından kullanılıyor.
_ERROR_HOTKEY_ALREADY_REGISTERED: int = 1409

# Modifier adı → Windows flag değeri
_MODIFIER_FLAGS: dict[str, int] = {
    "alt":   0x0001,   # MOD_ALT
    "ctrl":  0x0002,   # MOD_CONTROL
    "shift": 0x0004,   # MOD_SHIFT
    "win":   0x0008,   # MOD_WIN
}

# Tuş adı → Windows Virtual Key kodu
# Alfabe: 'a'-'z' → 0x41-0x5A (büyük harf VK kodları)
_VK_CODES: dict[str, int] = {
    # --- Alfabe ---
    **{chr(c): ord(chr(c).upper()) for c in range(ord("a"), ord("z") + 1)},
    # --- Rakamlar (üst sıra) ---
    **{str(i): 0x30 + i for i in range(10)},
    # --- Fonksiyon tuşları: F1=0x70 ... F12=0x7B ---
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    # --- Özel tuşlar ---
    "space":    0x20,
    "tab":      0x09,
    "enter":    0x0D,
    "escape":   0x1B,
    "esc":      0x1B,
    "home":     0x24,
    "end":      0x23,
    "pageup":   0x21,
    "pagedown": 0x22,
    "insert":   0x2D,
    "delete":   0x2E,
    "up":       0x26,
    "down":     0x28,
    "left":     0x25,
    "right":    0x27,
    # --- Numpad ---
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63,
    "num4": 0x64, "num5": 0x65, "num6": 0x66, "num7": 0x67,
    "num8": 0x68, "num9": 0x69,
}

# Uygulama içi hotkey ID'si.
# Windows her işlem içinde bağımsız ID alanı kullanır; başka uygulamalarla çakışmaz.
_HOTKEY_ID: int = 1


# ---------------------------------------------------------------------------
# Native Event Filter (iç sınıf)
# ---------------------------------------------------------------------------

class _HotkeyNativeFilter(QAbstractNativeEventFilter):
    """
    Windows WM_HOTKEY mesajlarını Qt event loop'undan önce yakalar.

    SADECE kendi hotkey ID'mize ait mesajları işler; diğer tüm native
    Windows mesajları (WM_PAINT, WM_SIZE vb.) dokunulmadan geçer.

    GC UYARISI:
        Bu nesne HotkeyManager._filter alanında tutulmalıdır.
        QApplication.installNativeEventFilter() C++ tarafında zayıf referans
        sakladığından, Python GC bu nesneyi silerse nativeEventFilter
        geçersiz belleğe erişir → bellek bozulması.
    """

    def __init__(self, hotkey_id: int, on_pressed) -> None:
        """
        Args:
            hotkey_id:  Dinlenecek WM_HOTKEY wParam değeri.
            on_pressed: Kısayol algılandığında çağrılacak callable
                        (hotkey_pressed.emit bağlanır).
        """
        super().__init__()
        self._hotkey_id = hotkey_id
        self._on_pressed = on_pressed

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        """
        Qt event dispatcher'ın her native Windows mesajında çağırır.

        Returns:
            (True,  0) → Mesaj tüketildi, Qt'ye iletilmiyor.
            (False, 0) → Mesaj geçirildi, Qt normal işlemeye devam eder.
        """
        # Sadece Windows mesaj kuyruğu tiplerini işle
        if event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0

        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception as exc:
            hk_err = HotkeyError(f"MSG parse hatası: {exc}")
            hk_err.__cause__ = exc
            logger.warning(str(hk_err))
            return False, 0

        # Sadece kendi hotkey ID'mize ait WM_HOTKEY mesajlarını işle
        if msg.message == _WM_HOTKEY:
            # Debug için metadata yazdır
            logger.debug(f"WM_HOTKEY alındı: event_type={event_type}, message={msg.message}, wParam={msg.wParam}, lParam={msg.lParam}")
            if msg.wParam == self._hotkey_id:
                logger.debug(f"WM_HOTKEY kendi hotkey'imiz! (ID={self._hotkey_id})")
                self._on_pressed()
                return True, 0  # Tükettik — Qt'ye iletme

        return False, 0  # Diğer tüm mesajlara dokunma


# ---------------------------------------------------------------------------
# HotkeyManager
# ---------------------------------------------------------------------------

class HotkeyManager(QObject):
    """
    Global kısayol yöneticisi.

    AppController yalnızca hotkey_pressed sinyalini görür;
    RegisterHotKey, WM_HOTKEY, VK kodu gibi Win32 detayları burada kapsüllenir.

    Kullanım (main.py'de):
        manager = HotkeyManager(config_manager)
        controller.register_hotkey_manager(manager)
        manager.setup()   # Filter kur + kısayolu register et
        ...
        manager.unregister()  # Uygulama kapanırken
    """

    # Kısayola başarılı basış → AppController.toggle_recording() tetikler
    hotkey_pressed = Signal()

    # Register başarısız olduğunda → kullanıcı dostu Türkçe hata mesajı
    registration_failed = Signal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._config = config_manager
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # Aktif kayıtlı kısayol bilgisi (rollback için saklanır)
        self._active_modifiers: list[str] = []
        self._active_key: str = ""
        self._is_registered: bool = False

        # Native event filter — GC'den korunmak için instance variable'da tut.
        # Bu referans setup() çağrısından uygulama kapanana kadar canlı kalır.
        self._filter = _HotkeyNativeFilter(
            hotkey_id=_HOTKEY_ID,
            on_pressed=self.hotkey_pressed.emit,
        )

        logger.debug("HotkeyManager oluşturuldu.")

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def setup(self) -> bool:
        """
        Native event filter'ı QApplication'a yükler ve
        config'deki kısayolu Windows'a register eder.

        AppController bunu register_hotkey_manager() ardından çağırır.
        QApplication.instance() var olmalıdır.

        Returns:
            True  → Kısayol başarıyla aktif.
            False → Register başarısız (uygulama çalışmaya devam eder,
                    kullanıcı farklı kısayol seçebilir).
        """
        app = QApplication.instance()
        if app is None:
            logger.error("setup(): QApplication bulunamadı — filter kurulamadı.")
            return False

        # Native event filter'ı Qt event loop'una bağla
        app.installNativeEventFilter(self._filter)
        logger.info("Native event filter kuruldu.")

        # Config'den kısayol kombinasyonunu oku ve register et
        cfg = self._config.config.hotkey
        success = self.register(cfg.modifiers, cfg.key)

        if success:
            logger.info(f"Kısayol hazır: {self.active_combo}")
        return success

    def register(self, modifiers: list[str], key: str) -> bool:
        """
        Belirtilen kısayolu Windows'a kaydet.

        Zaten kayıtlı bir kısayol varsa önce silinir, sonra yenisi kaydedilir.

        Args:
            modifiers: ["alt"], ["ctrl", "shift"] gibi modifier listesi.
            key:       "x", "f1", "space" gibi tuş adı.

        Returns:
            True  → Kısayol başarıyla kaydedildi.
            False → Kayıt başarısız (registration_failed sinyali yayıldı).
        """
        # Mevcut kayıt varsa temizle
        if self._is_registered:
            self._unregister_win32()

        # Tuş kodunu çöz
        vk = self._resolve_vk(key)
        if vk is None:
            msg = (
                f"'{key}' geçerli bir tuş adı değil. "
                f"Lütfen Ayarlar'dan geçerli bir kısayol seçin."
            )
            logger.error(f"register(): {msg}")
            self.registration_failed.emit(msg)
            return False

        # Modifier flag'lerini hesapla (MOD_NOREPEAT her zaman eklenir)
        mod_flags = self._build_modifier_flags(modifiers)

        # Windows'a kaydet
        result = bool(self._user32.RegisterHotKey(None, _HOTKEY_ID, mod_flags, vk))

        if result:
            self._active_modifiers = list(modifiers)
            self._active_key = key
            self._is_registered = True
            logger.info(
                f"Kısayol kaydedildi: {self.active_combo}"
                f" (flags={mod_flags:#06x}, vk={vk:#04x}, id={_HOTKEY_ID})"
            )
            return True
        else:
            error_code = self._kernel32.GetLastError()
            self._emit_register_error(modifiers, key, error_code)
            return False

    def unregister(self) -> None:
        """
        Kaydedilmiş kısayolu Windows'tan siler ve event filter'ı kaldırır.

        Uygulama kapanırken AppController.shutdown() tarafından çağrılır.
        Kayıtlı kısayol yoksa sessizce döner.
        """
        self._unregister_win32()

        app = QApplication.instance()
        if app is not None:
            try:
                app.removeNativeEventFilter(self._filter)
                logger.debug("Native event filter kaldırıldı.")
            except Exception as exc:
                hk_err = HotkeyError(f"removeNativeEventFilter hatası: {exc}")
                hk_err.__cause__ = exc
                logger.warning(str(hk_err))

    def change_hotkey(self, new_modifiers: list[str], new_key: str) -> bool:
        """
        Kısayolu atomik olarak değiştirir.

        Yeni kombinasyon register edilemezse eski çalışan kombinasyona
        otomatik rollback yapılır. Rollback da başarısız olursa kısayol
        geçici olarak devre dışı kalır ve log'a yazılır.

        Args:
            new_modifiers: Yeni modifier listesi.
            new_key:       Yeni tuş adı.

        Returns:
            True  → Yeni kısayol aktif.
            False → Register başarısız, rollback yapıldı (veya yapılamadı).
        """
        # Eski durumu yedekle (rollback için)
        old_modifiers = list(self._active_modifiers)
        old_key = self._active_key
        was_registered = self._is_registered

        combo_old = self._format_combo(old_modifiers, old_key) if was_registered else "(kayıtsız)"
        combo_new = self._format_combo(new_modifiers, new_key)
        logger.info(f"Kısayol değiştiriliyor: {combo_old} → {combo_new}")

        # Eski kaydı sil
        if was_registered:
            self._unregister_win32()

        # Yeni kısayolu dene
        if self.register(new_modifiers, new_key):
            logger.info(f"Kısayol değiştirildi: {combo_new}")
            return True

        # Yeni kısayol başarısız — rollback
        logger.warning(f"Yeni kısayol başarısız. Rollback: {combo_old}")

        if was_registered and old_key:
            if self.register(old_modifiers, old_key):
                logger.info(f"Rollback başarılı: {combo_old} aktif.")
                # Rollback'i kullanıcıya bildir
                self.registration_failed.emit(
                    f"'{combo_new}' kısayolu kaydedilemedi.\n"
                    f"Eski kısayol '{combo_old}' geri yüklendi."
                )
            else:
                logger.error(
                    f"Rollback da başarısız! Kısayol '{combo_old}' de register edilemedi. "
                    f"Kısayol şu an devre dışı."
                )
                self.registration_failed.emit(
                    f"'{combo_new}' kısayolu kaydedilemedi ve\n"
                    f"'{combo_old}' geri yüklenemedi.\n"
                    f"Lütfen Ayarlar'dan geçerli bir kısayol seçin."
                )
        else:
            self.registration_failed.emit(
                f"'{combo_new}' kısayolu kaydedilemedi.\n"
                f"Lütfen Ayarlar'dan geçerli bir kısayol seçin."
            )

        return False

    # ----------------------------------------------------------------
    # Public — Durum sorguları
    # ----------------------------------------------------------------

    @property
    def is_registered(self) -> bool:
        """Kısayol şu an aktif kayıtlı mı?"""
        return self._is_registered

    @property
    def active_combo(self) -> str:
        """
        Aktif kısayolun okunabilir gösterimi.
        Örnek: 'ALT+X', 'CTRL+SHIFT+F1'
        Kayıtlı değilse: '(kayıtlı değil)'
        """
        if not self._is_registered:
            return "(kayıtlı değil)"
        return self._format_combo(self._active_modifiers, self._active_key)

    # ----------------------------------------------------------------
    # Private — Win32 yardımcıları
    # ----------------------------------------------------------------

    def _unregister_win32(self) -> None:
        """Kayıtlı kısayolu Windows'tan siler. İç kullanım."""
        if not self._is_registered:
            return

        combo = self._format_combo(self._active_modifiers, self._active_key)
        result = bool(self._user32.UnregisterHotKey(None, _HOTKEY_ID))

        if result:
            logger.info(f"Kısayol kaydı silindi: {combo}")
        else:
            error = self._kernel32.GetLastError()
            logger.warning(f"UnregisterHotKey başarısız: {combo} (hata kodu: {error})")

        # Durumu her koşulda temizle (tekrar denemeyi engelle)
        self._is_registered = False
        self._active_modifiers = []
        self._active_key = ""

    def _build_modifier_flags(self, modifiers: list[str]) -> int:
        """
        Modifier string listesini Windows flag değerine dönüştürür.
        MOD_NOREPEAT her zaman eklenir.
        """
        flags = _MOD_NOREPEAT  # Basılı tutma tekrarını engelle
        for mod in modifiers:
            flag = _MODIFIER_FLAGS.get(mod.lower())
            if flag is None:
                logger.warning(f"Bilinmeyen modifier: '{mod}' yoksayıldı.")
            else:
                flags |= flag
        return flags

    def _resolve_vk(self, key: str) -> int | None:
        """
        Tuş adını Windows Virtual Key koduna çevirir.

        Args:
            key: 'x', 'f1', 'space' gibi tuş adı (büyük/küçük harf duyarsız).

        Returns:
            int  → VK kodu (0x00-0xFF)
            None → Bilinmeyen tuş adı
        """
        return _VK_CODES.get(key.lower())

    @staticmethod
    def _format_combo(modifiers: list[str], key: str) -> str:
        """['alt', 'ctrl'], 'x'  →  'ALT+CTRL+X'"""
        parts = [m.upper() for m in modifiers] + [key.upper()]
        return "+".join(parts)

    def _emit_register_error(
        self,
        modifiers: list[str],
        key: str,
        error_code: int,
    ) -> None:
        """
        RegisterHotKey başarısız olduğunda:
        - Windows hata kodunu log'a yazar.
        - Kullanıcı dostu Türkçe mesajla registration_failed sinyali yayar.
        """
        combo = self._format_combo(modifiers, key)

        if error_code == _ERROR_HOTKEY_ALREADY_REGISTERED:
            user_msg = (
                f"'{combo}' kısayolu başka bir uygulama tarafından kullanılıyor.\n"
                f"Lütfen Ayarlar'dan farklı bir kısayol seçin."
            )
        else:
            user_msg = (
                f"'{combo}' kısayolu kaydedilemedi.\n"
                f"Windows hata kodu: {error_code}.\n"
                f"Farklı bir kısayol deneyin veya uygulamayı yeniden başlatın."
            )

        logger.error(
            f"RegisterHotKey başarısız: {combo}"
            f" | Windows hata kodu: {error_code}"
            f" | Açıklama: "
            + ("Kısayol zaten alınmış." if error_code == _ERROR_HOTKEY_ALREADY_REGISTERED
               else "Bilinmeyen hata.")
        )
        self.registration_failed.emit(user_msg)
