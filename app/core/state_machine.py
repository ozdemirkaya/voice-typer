"""
app/core/state_machine.py
==========================
Voice Typer uygulama durum makinesi (State Machine).

Qt bağımlılığı YOKTUR — pure Python sınıfı.
Bu sayede bağımsız olarak test edilebilir ve AppController'dan ayrı tutulabilir.

Durumlar (AppState):
    IDLE           → Hazır, kullanıcı girişi bekleniyor.
    RECORDING      → Mikrofon aktif, ses kaydediliyor.
    PROCESSING     → Kayıt tamamlandı, STT işleniyor.
    LOADING_MODEL  → faster-whisper modeli ilk kez yükleniyor.
    ERROR          → Bir hata oluştu, kullanıcı bilgilendirildi.

Geçerli geçişler:
    IDLE           → RECORDING, LOADING_MODEL, ERROR
    RECORDING      → PROCESSING, IDLE (iptal), ERROR
    PROCESSING     → IDLE, ERROR
    LOADING_MODEL  → IDLE, ERROR
    ERROR          → IDLE (hata giderildi/kullanıcı onayladı)
"""

from enum import Enum
from typing import Callable

from app.services.logger import get_logger

logger = get_logger(__name__)


class AppState(Enum):
    """Uygulamanın anlık çalışma durumu."""
    IDLE          = "idle"
    RECORDING     = "recording"
    PROCESSING    = "processing"
    LOADING_MODEL = "loading_model"
    ERROR         = "error"


# Geçerli durum geçişleri tablosu.
# Anahtar: mevcut durum → Değer: geçiş yapılabilecek durumlar kümesi.
_VALID_TRANSITIONS: dict[AppState, set[AppState]] = {
    AppState.IDLE:          {AppState.RECORDING, AppState.LOADING_MODEL, AppState.ERROR},
    AppState.RECORDING:     {AppState.PROCESSING, AppState.IDLE, AppState.ERROR},
    AppState.PROCESSING:    {AppState.LOADING_MODEL, AppState.IDLE, AppState.ERROR},
    AppState.LOADING_MODEL: {AppState.PROCESSING, AppState.IDLE, AppState.ERROR},
    AppState.ERROR:         {AppState.IDLE},
}


class StateMachine:
    """
    Geçiş doğrulamalı deterministik durum makinesi.

    Geçersiz geçiş denemeleri sessizce reddedilmez — loglanır ve False döner.
    Bu sayede hata ayıklama kolaylaşır ve beklenmedik davranışlar tespit edilir.

    Kullanım:
        sm = StateMachine()
        sm.transition(AppState.RECORDING)   # True (IDLE → RECORDING geçerli)
        sm.transition(AppState.IDLE)        # True (RECORDING → IDLE geçerli)
        sm.transition(AppState.PROCESSING)  # False (IDLE → PROCESSING GEÇERSİZ)
    """

    def __init__(
        self,
        initial_state: AppState = AppState.IDLE,
        on_transition: Callable[[AppState, AppState], None] | None = None,
    ) -> None:
        """
        Args:
            initial_state:   Başlangıç durumu.
            on_transition:   Başarılı geçişlerde çağrılacak callback(old, new).
                             AppController bunu Qt signal emit için kullanır.
        """
        self._state = initial_state
        self._on_transition = on_transition
        logger.debug(f"StateMachine başlatıldı: initial={initial_state.value}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> AppState:
        """Anlık durum (read-only)."""
        return self._state

    def transition(self, new_state: AppState, reason: str = "") -> bool:
        """
        Yeni duruma geçiş dener.

        Args:
            new_state: Geçilmek istenen durum.
            reason:    Loglama için isteğe bağlı neden açıklaması.

        Returns:
            True  → Geçiş başarılı.
            False → Geçiş geçersiz, durum değişmedi.
        """
        if self._state == new_state:
            logger.debug(f"State geçişi atlandı: zaten {new_state.value} durumunda.")
            return True  # Aynı duruma geçiş "başarılı" sayılır

        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            logger.warning(
                f"Geçersiz state geçişi engellendi: "
                f"{self._state.value} → {new_state.value}"
                + (f" (neden: {reason})" if reason else "")
                + f" | İzin verilenler: {[s.value for s in allowed]}"
            )
            return False

        old_state = self._state
        self._state = new_state

        log_msg = f"State: {old_state.value} → {new_state.value}"
        if reason:
            log_msg += f" [{reason}]"
        logger.info(log_msg)

        if self._on_transition:
            self._on_transition(old_state, new_state)

        return True

    def can_transition(self, new_state: AppState) -> bool:
        """Belirtilen duruma geçişin mümkün olup olmadığını döndürür (durum değiştirmez)."""
        return new_state in _VALID_TRANSITIONS.get(self._state, set())

    def is_in(self, *states: AppState) -> bool:
        """Anlık durumun verilen durumlardan biri olup olmadığını döndürür."""
        return self._state in states

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state.value})"
