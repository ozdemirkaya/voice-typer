"""
app/core/app_controller.py
===========================
Uygulamanın merkezi koordinasyon katmanı.

AppController şunlardan sorumludur:
- Durum makinesini (StateMachine) yönetmek ve geçişleri koordine etmek.
- UI (TrayIcon, Overlay, SettingsWindow) ile servisler arasında köprü kurmak.
- Qt Signal/Slot altyapısını kurmak (ileriki aşamalar için hazır hook'lar).
- Component lifecycle yönetimi (başlatma, durdurma, temiz kapatma).

AppController Business Logic İÇERMEZ:
- Ses kaydı mantığı → AudioRecorder (Phase 4)
- STT mantığı       → FasterWhisperProvider (Phase 5)
- Metin enjeksiyonu → TextInjector + ClipboardManager (Phase 6)
- Hotkey yönetimi   → HotkeyManager (Phase 3)

Veri akışı (tam implementasyon sonrası):
    HotkeyManager.hotkey_pressed
        → AppController.toggle_recording()
            → [IDLE→RECORDING] AudioRecorder.start(target_hwnd)
            → [RECORDING→PROCESSING] AudioRecorder.stop()
                → STTWorker.run(audio_path)
                    → AppController.on_transcription_done(text, hwnd)
                        → [PROCESSING→IDLE] TextInjector.inject(text, hwnd)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from app.core.state_machine import AppState, StateMachine
from app.core.operation import OperationContext
from app.services.logger import get_logger

if TYPE_CHECKING:
    from app.services.config_manager import ConfigManager
    from app.ui.tray_icon import TrayIcon

logger = get_logger(__name__)


class AppController(QObject):
    """
    Merkezi uygulama kontrolcüsü.

    Tüm bileşenler bu sınıf üzerinden haberleşir; doğrudan birbirlerine
    referans tutmazlar. Bu yaklaşım bağımlılıkları minimize eder ve
    test edilebilirliği artırır.

    Phase 2 kapsamı:
    - StateMachine kurulumu ve yönetimi
    - TrayIcon bağlantısı (state değişikliklerini yansıtır)
    - Phase 3+ için stub hook metodları

    Phase 3+ kapsamı (stub'lar şimdi tanımlanıyor, implement edilmiyor):
    - HotkeyManager bağlantısı
    - AudioRecorder bağlantısı
    - STTProvider bağlantısı
    - TextInjector bağlantısı
    """

    # ----------------------------------------------------------------
    # Qt Sinyalleri
    # ----------------------------------------------------------------

    # Durum her değiştiğinde yayılır — tüm UI bileşenleri buna bağlanabilir
    state_changed = Signal(AppState)

    # Herhangi bir bileşenden hata geldiğinde yayılır
    error_occurred = Signal(str)

    # Phase 3: Hotkey veya tray menüsünden kayıt isteği geldi
    recording_toggled = Signal()

    # Phase 4: Ses kaydı tamamlandı (audio dosya yolu + hedef pencere handle)
    recording_finished = Signal(str, int)   # audio_path: str, target_hwnd: int

    # Phase 5: STT sonucu hazır
    transcription_ready = Signal(str, int)  # text: str, target_hwnd: int

    # Phase 5: STT hata verdi
    transcription_failed = Signal(str)      # error_message: str

    # Phase 5: Model yükleme tamamlandı / başladı
    model_loading_started = Signal()
    model_loading_finished = Signal(bool)   # success: bool

    def __init__(
        self,
        config_manager: ConfigManager,
        tray_icon: TrayIcon,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self._config = config_manager
        self._tray = tray_icon

        # --- Durum makinesi ---
        self._sm = StateMachine(
            initial_state=AppState.IDLE,
            on_transition=self._on_state_changed_internal,  # StateMachine callback → Qt signal
        )

        # --- Phase 3+ bileşen referansları (başlangıçta None) ---
        # Her phase tamamlandığında ilgili referans set edilir.
        self._hotkey_manager = None    # Phase 3: HotkeyManager
        self._audio_recorder = None    # Phase 4: AudioRecorder
        self._stt_provider = None      # Phase 5: BaseTranscriptionProvider
        self._text_injector = None     # Phase 6: TextInjector

        self._shutting_down: bool = False
        self._current_op: OperationContext | None = None
        self._op_counter: int = 0

        # Hata durumunda son hata mesajını sakla
        self._last_error: str = ""

        self._connect_internal_signals()
        logger.info(f"AppController hazır. Başlangıç state: {self._sm.state.value}")

    # ----------------------------------------------------------------
    # Public — Durum sorguları
    # ----------------------------------------------------------------

    @property
    def state(self) -> AppState:
        """Anlık uygulama durumu."""
        return self._sm.state

    def is_idle(self) -> bool:
        return self._sm.is_in(AppState.IDLE)

    def is_recording(self) -> bool:
        return self._sm.is_in(AppState.RECORDING)

    def is_processing(self) -> bool:
        return self._sm.is_in(AppState.PROCESSING)

    def is_busy(self) -> bool:
        """Kullanıcı girişi kabul edilemiyen bir durumda mı?"""
        return self._sm.is_in(AppState.RECORDING, AppState.PROCESSING, AppState.LOADING_MODEL)

    # ----------------------------------------------------------------
    # Public — Kayıt kontrolü (Phase 3 bağlantı noktası)
    # ----------------------------------------------------------------

    def toggle_recording(self) -> None:
        """
        Kayıt başlat/durdur toggle.
        Rapid Hotkey / Race condition korumalıdır.
        """
        if self._shutting_down:
            return

        if self._sm.is_in(AppState.IDLE):
            self._do_start_recording()
        elif self._sm.is_in(AppState.RECORDING):
            self._do_stop_recording()
        elif self._sm.is_in(AppState.ERROR):
            logger.info("Hotkey pressed in ERROR state. Recovering to IDLE.")
            self.recover_from_error()
        else:
            logger.info(
                f"Rapid Hotkey: '{self._sm.state.value}' durumunda kayıt işlemi yoksayıldı."
            )

    def cancel_recording(self) -> None:
        """
        Aktif kaydı iptal eder ve IDLE'a döner.
        Kullanıcı ESC'ye basarsa veya tray menüsünden iptal ederse çağrılır.
        """
        if self._sm.is_in(AppState.RECORDING):
            logger.info("Kayıt kullanıcı tarafından iptal edildi.")
            self._transition(AppState.IDLE, reason="kullanıcı iptali")
            # Phase 4: self._audio_recorder.cancel()
        else:
            logger.debug(f"cancel_recording() geçersiz durumda: {self._sm.state.value}")

    # ----------------------------------------------------------------
    # Public — Phase 4+ callback hook'ları
    # ----------------------------------------------------------------

    def on_recording_finished(self, result, op_id: int) -> None:
        """
        AudioRecorder'dan gelen sonuc. Stale callback korumali.
        """
        if self._shutting_down or self._current_op is None or op_id != self._current_op.operation_id:
            logger.warning(f"Stale callback iptal edildi (op_id={op_id}, current={getattr(self._current_op, 'operation_id', None)}).")
            # cleanup orphans
            if result.path.exists():
                try: result.path.unlink()
                except Exception: pass
            return

        if not self._sm.is_in(AppState.PROCESSING):
            logger.warning(
                f"on_recording_finished() beklenmedik durumda çağrıldı: {self._sm.state.value}"
            )
            return

        if not result.is_valid:
            logger.info("Kayıt eşik süreden kısa olduğu için iptal edildi (Kazara basma).")
            self._transition(AppState.IDLE, reason="kısa kayıt")
            # Kisa kaydi hemen sil
            if result.path.exists():
                try:
                    result.path.unlink()
                except Exception:
                    pass
            self._current_op = None
            return

        logger.debug(f"Kayıt teslim alındı: {result.path} | süre={result.duration_seconds:.2f}s")
        
        if self._stt_provider is None:
            logger.error("STT Provider bulunamadi!")
            self._transition(AppState.IDLE, reason="STT provider eksik")
            self._current_op = None
            return

        self._current_op.recording_path = result.path
        logger.info("Transcription işlemi başlatılıyor...")
        # STT'ye islem yollanirken op_id'yi de gonderiyoruz
        self._stt_provider.transcribe(result, op_id)

    def on_recording_failed(self, error_message: str, op_id: int) -> None:
        """AudioRecorder hata durumunda çağrılır. Stale callback korumalı."""
        if self._shutting_down or self._current_op is None or op_id != self._current_op.operation_id:
            logger.warning(f"Stale recording_failed callback iptal edildi (op_id={op_id}).")
            return
            
        logger.error(f"Kayıt hatası: {error_message}")
        self.error_occurred.emit(error_message)


    def on_transcription_done(self, result, op_id: int) -> None:
        """
        STT sonucunu al. Stale callback korumali.
        """
        if self._shutting_down or self._current_op is None or op_id != self._current_op.operation_id:
            logger.warning(f"Stale STT callback iptal edildi (op_id={op_id}).")
            return

        # Eger su an hala model yukleniyor durumundaysak veya PROCESSING'deysek devam edebiliriz
        if not self._sm.is_in(AppState.PROCESSING, AppState.LOADING_MODEL):
            logger.warning(
                f"on_transcription_done() beklenmedik durumda: {self._sm.state.value}"
            )
            return

        logger.info(f"Transkripsiyon tamamlandı ({result.processing_time_seconds:.2f}s).")
        logger.debug(f"Metin uzunlugu: {len(result.text)} karakter")
        
        # Temp WAV temizligi
        if self._current_op.recording_path and not self._config.config.audio.keep_recordings:
            try:
                if self._current_op.recording_path.exists():
                    self._current_op.recording_path.unlink()
                    logger.debug("Temp WAV dosyası silindi.")
            except Exception as e:
                logger.warning(f"Temp WAV silinemedi: {e}")

        # Phase 6: Hedef pencereye yazdirma
        if self._text_injector and self._current_op.target_hwnd:
            self._text_injector.inject(result.text, self._current_op.target_hwnd)
        else:
            self.transcription_ready.emit(result.text, getattr(self._current_op, 'target_hwnd', 0))

        self._transition(AppState.IDLE, reason="transkripsiyon başarılı (islem tamamlandi)")
        self._current_op = None

        # Phase 6: self._text_injector.inject(text, target_hwnd)

    def on_transcription_error(self, error_message: str, op_id: int) -> None:
        if self._shutting_down or self._current_op is None or op_id != self._current_op.operation_id:
            return
        self.error_occurred.emit(error_message)

    def on_model_load_started(self) -> None:
        """
        Phase 5 bağlantı noktası.
        Model yükleme başladığında çağrılır.
        """
        self._transition(AppState.LOADING_MODEL, reason="model yükleniyor")
        self.model_loading_started.emit()

    def on_model_load_finished(self, success: bool, error: str = "") -> None:
        """
        Phase 5 bağlantı noktası.
        Model yükleme tamamlandığında (başarı veya hata) çağrılır.
        """
        if success:
            logger.info("Model başarıyla yüklendi, transcription'a devam ediliyor...")
            self._transition(AppState.PROCESSING, reason="model yüklendi")
        else:
            logger.error(f"Model yüklenemedi: {error}")
            self.error_occurred.emit(f"Model yüklenemedi:\n{error}")
        self.model_loading_finished.emit(success)

    # ----------------------------------------------------------------
    # Public — Hata yönetimi
    # ----------------------------------------------------------------

    def recover_from_error(self) -> None:
        """
        Hata durumundan IDLE'a döner. (Phase 8: State Machine Recovery)
        """
        if self._sm.is_in(AppState.ERROR):
            logger.info("Hata durumundan kurtarılıyor → IDLE")
            # 1. Yeni operation kabul etme (shutdown'da yapiliyor, burada gerek yok)
            # 2. Current operation'i invalidate et
            self._current_op = None
            
            # 3. Audio cleanup
            if self._audio_recorder:
                try: self._audio_recorder.stop()
                except Exception: pass
                
            # 4. STT worker cleanup
            # Eger STT tarafinda model vs sismisse burada cagrilabilir (ileride cancel() destegi gelirse)
            
            # 5. Gerekli temp cleanup (on_recording_finished icinde handle ediliyor eger orphaned ise)
            
            # 6. Kontrollü ERROR -> IDLE transition
            self._transition(AppState.IDLE, reason="kullanıcı hatayı onayladı (recovery)")
        else:
            logger.debug(f"recover_from_error(): hata durumunda değil ({self._sm.state.value})")

    # ----------------------------------------------------------------
    # Public — Phase 3+ bileşen kayıt API'si
    # ----------------------------------------------------------------

    def register_hotkey_manager(self, manager) -> None:
        """
        Phase 3: HotkeyManager kaydı.

        Bağlanan sinyaller:
        - manager.hotkey_pressed       → self.toggle_recording()
        - manager.registration_failed  → tray bildirimi (Win32 hatası kullanıcıya gösterilir)
        """
        self._hotkey_manager = manager
        manager.hotkey_pressed.connect(self.toggle_recording)
        manager.registration_failed.connect(self._on_hotkey_registration_failed)
        logger.info("HotkeyManager kaydedildi.")

    def _on_hotkey_registration_failed(self, message: str) -> None:
        """
        Kısayol register başarısız olduğunda kullanıcıyı tray bildirimiyle bilgilendirir.
        Uygulama çalışmaya devam eder; kullanıcı Ayarlar'dan farklı kısayol seçebilir.
        """
        from PySide6.QtWidgets import QSystemTrayIcon
        logger.warning(f"Kısayol register hatası: {message[:100]}")
        self._tray.notify(
            "Voice Typer — Kısayol Hatası",
            message,
            icon=QSystemTrayIcon.MessageIcon.Warning,
            duration_ms=8000,
        )

    def register_audio_recorder(self, recorder) -> None:
        """Phase 4: AudioRecorder kaydı."""
        self._audio_recorder = recorder
        recorder.recording_stopped.connect(self.on_recording_finished)
        recorder.recording_failed.connect(self.on_recording_failed)
        logger.info("AudioRecorder kaydedildi.")


    def register_stt_provider(self, worker) -> None:
        """Phase 5: STT Worker kaydı."""
        self._stt_provider = worker
        worker.transcription_done.connect(self.on_transcription_done)
        worker.transcription_error.connect(self.on_transcription_error)
        worker.model_load_started.connect(self.on_model_load_started)
        worker.model_load_finished.connect(self.on_model_load_finished)
        logger.info("STT Provider kaydedildi.")

    def register_text_injector(self, injector) -> None:
        """Phase 6: TextInjector kaydı."""
        self._text_injector = injector
        # TextInjector'un islem sonucunu dinleyebiliriz (opsiyonel tray bildirimi icin)
        injector.injection_done.connect(self._on_injection_done)
        logger.info("TextInjector kaydedildi.")

    def _on_injection_done(self, success: bool, message: str) -> None:
        if not success:
            # Pano kopyalamasi vs icin kucuk bir info
            self._tray.notify("Voice Typer", message, duration_ms=2000)

    # ----------------------------------------------------------------
    # Public — Lifecycle
    # ----------------------------------------------------------------

    def shutdown(self) -> None:
        """
        Uygulama kapanmadan önce tüm bileşenleri temiz biçimde durdurur.
        """
        import threading
        logger.info("[Shutdown] requested")
        logger.info(f"[Shutdown] active threads before: {[t.name for t in threading.enumerate()]}")
        
        self._shutting_down = True
        self._current_op = None

        if self._hotkey_manager is not None:
            try:
                logger.info("[Shutdown] hotkey unregister starting")
                self._hotkey_manager.unregister()
                logger.info("[Shutdown] hotkey unregister completed")
            except Exception as exc:
                logger.warning(f"HotkeyManager kapatma hatası: {exc}")

        if self._audio_recorder is not None:
            try:
                logger.info("[Shutdown] audio recorder stopping")
                self._audio_recorder.stop()
                logger.info("[Shutdown] audio recorder completed")
            except Exception as exc:
                logger.warning(f"AudioRecorder kapatma hatası: {exc}")

        if self._stt_provider is not None:
            try:
                logger.info("[Shutdown] STT worker stopping")
                self._stt_provider.shutdown()
                logger.info("[Shutdown] STT worker completed")
            except Exception as exc:
                logger.warning(f"STT Provider kapatma hatası: {exc}")

        if hasattr(self, '_tray'):
            self._tray.hide()
            logger.info("[Shutdown] tray hidden")

        logger.info(f"[Shutdown] active threads after: {[t.name for t in threading.enumerate()]}")
        logger.info("[Shutdown] finished")

    # ----------------------------------------------------------------
    # Internal — Durum yönetimi
    # ----------------------------------------------------------------

    def _transition(self, new_state: AppState, reason: str = "") -> bool:
        """
        StateMachine üzerinden geçiş yapar.
        Başarısız geçişlerde False döner (log StateMachine tarafından yazılır).
        """
        return self._sm.transition(new_state, reason=reason)

    def _on_state_changed_internal(self, old: AppState, new: AppState) -> None:
        """
        StateMachine'in on_transition callback'i.
        Qt signal olarak yayılır — TrayIcon ve diğer UI bileşenleri buraya bağlanır.
        """
        self.state_changed.emit(new)

    # ----------------------------------------------------------------
    # Internal — Kayıt implementasyon stub'ları
    # ----------------------------------------------------------------

    def _do_start_recording(self) -> None:
        """
        Kayıt başlatma.
        AudioRecorder.start() başarılı olursa RECORDING state'ine geçeriz.
        """
        if self._audio_recorder is None:
            logger.error("AudioRecorder kaydedilmedi!")
            return

        self._op_counter += 1
        op_id = self._op_counter

        # Hedef pencereyi kaydet (Kullanici o an nereye odaklanmissa oraya yazilacak)
        import win32gui
        try:
            target_hwnd = win32gui.GetForegroundWindow()
        except Exception:
            target_hwnd = 0

        # Mikrofon başlatılamazsa AudioRecorder False döner ve hata sinyali yayar
        if self._audio_recorder.start(op_id):
            if self._transition(AppState.RECORDING, reason="kullanıcı başlattı"):
                logger.info(f"Kayıt başladı (op_id={op_id}).")
                self._current_op = OperationContext(operation_id=op_id, target_hwnd=target_hwnd)
            else:
                # Eger transition basarisiz olursa kaydi geri durdur
                self._audio_recorder.stop()

    def _do_stop_recording(self) -> None:
        """
        Kaydı durdur ve STT'ye gönder.
        Phase 4: AudioRecorder.stop() çağrısı diske yazma işleminin bitmesini tetikler.
        """
        if not self._transition(AppState.PROCESSING, reason="kullanıcı durdurdu"):
            return

        logger.info("Kayıt durduruldu, WAV dosyasının diske yazılması bekleniyor...")
        if self._audio_recorder:
            self._audio_recorder.stop()

    # ----------------------------------------------------------------
    # Internal — Sinyal bağlantıları
    # ----------------------------------------------------------------

    def _connect_internal_signals(self) -> None:
        """İç sinyal/slot bağlantılarını kurar."""
        # state_changed → TrayIcon güncelleme
        self.state_changed.connect(self._update_tray_state)

        # error_occurred → ERROR state'e geç + tray bildirimi
        self.error_occurred.connect(self._on_error_signal)

    def _update_tray_state(self, state: AppState) -> None:
        """State değişikliğini TrayIcon'a yansıtır."""
        tray_state_map = {
            AppState.IDLE:          "idle",
            AppState.RECORDING:     "recording",
            AppState.PROCESSING:    "processing",
            AppState.LOADING_MODEL: "loading",
            AppState.ERROR:         "error",
        }
        tray_state = tray_state_map.get(state, "idle")
        self._tray.set_state(tray_state)

        # Tray menüsündeki kayıt butonu metnini güncelle
        self._tray.update_record_action(state)

    def _on_error_signal(self, message: str) -> None:
        """error_occurred sinyali alındığında ERROR state'e geç."""
        self._last_error = message
        if not self._sm.is_in(AppState.ERROR):
            self._transition(AppState.ERROR, reason=message[:80])
        self._tray.notify(
            "Voice Typer — Hata",
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            duration_ms=5000,
        )
