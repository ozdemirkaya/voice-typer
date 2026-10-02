"""
app/ui/tray_icon.py
====================
Windows sistem çubuğu (system tray) ikonu ve menüsü.

Phase 1: Temel iskelet — ikon, durum mekanizması, menü.
Kayıt/STT entegrasyonu ileriki aşamalarda eklenecek.

Durum makinesi:
    idle       → Hazır (yeşil)
    recording  → Kayıt yapılıyor (kırmızı)
    processing → İşleniyor (turuncu)
    loading    → Model yükleniyor (mavi)
    error      → Hata (gri)
"""

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.core.state_machine import AppState
from app.services.config_manager import ConfigManager
from app.services.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# İkon oluşturucu (dosya yokken programatik fallback)
# ---------------------------------------------------------------------------

def _make_circle_icon(color_hex: str, size: int = 32) -> QIcon:
    """
    Belirtilen renkte dolu daire ikonu oluşturur.
    Gerçek ikon dosyaları eklenene kadar placeholder olarak kullanılır.

    Args:
        color_hex: "#RRGGBB" formatında renk.
        size:      Piksel cinsinden ikon boyutu.

    Returns:
        QIcon: Oluşturulan ikon.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color_hex)))
    painter.setPen(Qt.PenStyle.NoPen)
    margin = 2
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()

    return QIcon(pixmap)


def _load_icon(assets_dir: Path, filename: str, fallback_color: str) -> QIcon:
    """
    Önce assets klasöründen ikon dosyasını yüklemeyi dener.
    Dosya yoksa programatik renkli daire döndürür.
    """
    icon_path = assets_dir / filename
    if icon_path.exists():
        return QIcon(str(icon_path))
    return _make_circle_icon(fallback_color)


# ---------------------------------------------------------------------------
# TrayIcon
# ---------------------------------------------------------------------------

class TrayIcon(QSystemTrayIcon):
    """
    Voice Typer sistem çubuğu ikonu.

    Sorumluluklar:
    - Uygulamanın anlık durumunu (idle/recording/processing/...) görsel olarak göstermek.
    - Kullanıcıya sağ tık menüsü sunmak.
    - Durum bildirimleri (showMessage) göstermek.

    Bağlantılar (ileriki aşamalarda):
    - record_action.triggered → AppController.toggle_recording()
    - settings_action.triggered → SettingsWindow.show()
    """

    # Durum → (renk, tooltip metni, menü etiketi)
    _STATE_INFO: dict[str, tuple[str, str, str]] = {
        "idle":       ("#4CAF50", "Voice Typer — Hazır",               "● Hazır"),
        "recording":  ("#F44336", "Voice Typer — Kayıt yapılıyor",     "🔴 Kayıt yapılıyor..."),
        "processing": ("#FF9800", "Voice Typer — İşleniyor",           "⏳ İşleniyor..."),
        "loading":    ("#2196F3", "Voice Typer — Model yükleniyor",    "🔵 Model yükleniyor..."),
        "error":      ("#9E9E9E", "Voice Typer — Hata oluştu",         "⚠  Hata"),
    }

    # Kullanıcı tray menüsünden kayıt isteğinde bulundu.
    # AppController.toggle_recording()'e bağlanır.
    record_requested = Signal()

    # Kullanıcı hata durumundan kurtarma istedi (ERROR state’de “Tekrar Dene”).
    recover_requested = Signal()
    
    settings_requested = Signal()

    def __init__(self, config_manager: ConfigManager, parent=None) -> None:
        super().__init__(parent)

        self._config_manager = config_manager
        self._state: str = "idle"

        # Assets klasörü (Phase 1'de ikonlar henüz yoktur, fallback kullanılır)
        self._assets_dir = config_manager.app_dir / "app" / "assets"

        self._icons = self._preload_icons()
        self._setup_icon()
        self._setup_menu()

        logger.info("TrayIcon oluşturuldu.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """
        Tray ikonunu ve durum metnini günceller.

        Args:
            state: "idle" | "recording" | "processing" | "loading" | "error"
        """
        if state not in self._STATE_INFO:
            logger.warning(f"Bilinmeyen tray durumu: '{state}'")
            return

        self._state = state
        _, tooltip, menu_label = self._STATE_INFO[state]

        self.setIcon(self._icons[state])
        self.setToolTip(tooltip)
        self._status_action.setText(menu_label)

        logger.debug(f"Tray durumu güncellendi: {state}")

    def notify(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        duration_ms: int = 3000,
    ) -> None:
        """
        Sistem çubuğu üzerinde balon bildirim gösterir.

        Args:
            title:       Bildirim başlığı.
            message:     Bildirim içeriği.
            icon:        Bildirim ikonu türü.
            duration_ms: Görünme süresi (ms).
        """
        self.showMessage(title, message, icon, duration_ms)

    def update_record_action(self, state: AppState) -> None:
        """
        Tray menüsündeki kayıt butonunun metin ve aktifliğini
        anlık AppState'e göre günceller.

        AppController bunu state_changed sinyaline bağlar.
        """
        from app.core.state_machine import AppState as _AppState
        labels: dict[AppState, tuple[str, bool]] = {
            _AppState.IDLE:          ("🎙  Kayıt Başlat  (Alt+X)",   True),
            _AppState.RECORDING:     ("⏹  Kaydı Durdur  (Alt+X)",   True),
            _AppState.PROCESSING:    ("⏳  İşleniyor...",             False),
            _AppState.LOADING_MODEL: ("🔵  Model yükleniyor...",      False),
            _AppState.ERROR:         ("⚠  Hata — Tekrar Dene",      True),
        }
        label, enabled = labels.get(state, ("🎙  Kayıt Başlat  (Alt+X)", True))
        self._record_action.setText(label)
        self._record_action.setEnabled(enabled)

        # ERROR durumunda butonu recover_requested’a yönlendir
        try:
            self._record_action.triggered.disconnect()
        except RuntimeError:
            pass  # Bağlı sinyal yoksa hata vermez

        if state == _AppState.ERROR:
            self._record_action.triggered.connect(self.recover_requested.emit)
        else:
            self._record_action.triggered.connect(self.record_requested.emit)

    # ------------------------------------------------------------------
    # Internal — Icon
    # ------------------------------------------------------------------

    def _preload_icons(self) -> dict[str, QIcon]:
        """
        Tüm durum ikonlarını başlangıçta yükler/oluşturur.
        İleride gerçek .ico dosyaları assets/ klasörüne koyulabilir.
        """
        icon_files = {
            "idle":       ("icon.ico",            "#4CAF50"),
            "recording":  ("icon_recording.ico",  "#F44336"),
            "processing": ("icon_processing.ico", "#FF9800"),
            "loading":    ("icon_loading.ico",    "#2196F3"),
            "error":      ("icon_error.ico",      "#9E9E9E"),
        }
        return {
            state: _load_icon(self._assets_dir, filename, color)
            for state, (filename, color) in icon_files.items()
        }

    def _setup_icon(self) -> None:
        """Başlangıç ikonunu ve tooltip'i ayarlar."""
        _, tooltip, _ = self._STATE_INFO["idle"]
        self.setIcon(self._icons["idle"])
        self.setToolTip(tooltip)

    # ------------------------------------------------------------------
    # Internal — Menu
    # ------------------------------------------------------------------

    def _setup_menu(self) -> None:
        """Sağ tık bağlam menüsünü oluşturur."""
        menu = QMenu()

        # --- Durum göstergesi (tıklanamaz) ---
        self._status_action = menu.addAction("● Hazır")
        self._status_action.setEnabled(False)

        menu.addSeparator()

        # --- Kayıt ---
        self._record_action = menu.addAction("🎙  Kayıt Başlat  (Alt+X)")
        self._record_action.triggered.connect(self.record_requested.emit)
        # Phase 3 tamamlanana kadar tray menüsü üzerinden toggle test edilebilir:
        self._record_action.setEnabled(True)

        menu.addSeparator()

        # --- Ayarlar ---
        self._settings_action = menu.addAction("⚙  Ayarlar")
        self._settings_action.setEnabled(True)  # Phase 7
        self._settings_action.triggered.connect(self.settings_requested.emit)

        menu.addSeparator()

        # --- Log görüntüleyici ---
        log_action = menu.addAction("📄  Log Dosyasını Aç")
        log_action.triggered.connect(self._open_log_file)

        menu.addSeparator()

        # --- Çıkış ---
        quit_action = menu.addAction("✕  Çıkış")
        quit_action.triggered.connect(self._on_quit)

        self.setContextMenu(menu)

    # ------------------------------------------------------------------
    # Internal — Slots
    # ------------------------------------------------------------------

    def _open_log_file(self) -> None:
        """Log dosyasını Notepad ile açar."""
        log_file = self._config_manager.app_dir / "logs" / "voicetyper.log"
        if log_file.exists():
            try:
                subprocess.Popen(["notepad.exe", str(log_file)])
                logger.debug(f"Log dosyası açıldı: {log_file}")
            except OSError as exc:
                logger.error(f"Log dosyası açılamadı: {exc}")
                self.notify(
                    "Voice Typer",
                    f"Log dosyası açılamadı:\n{exc}",
                    QSystemTrayIcon.MessageIcon.Warning,
                )
        else:
            self.notify(
                "Voice Typer",
                "Henüz log dosyası oluşturulmamış.",
                QSystemTrayIcon.MessageIcon.Information,
            )

    def _on_quit(self) -> None:
        """Kullanıcı Çıkış'a tıkladığında uygulamayı kapatır."""
        logger.info("[Shutdown] tray exit triggered")
        logger.info("[Shutdown] QApplication.quit requested")
        QApplication.quit()
