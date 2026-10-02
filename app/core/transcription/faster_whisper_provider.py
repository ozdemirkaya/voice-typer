"""
app/core/transcription/faster_whisper_provider.py
===================================================
faster-whisper (CTranslate2) motorunu kullanarak STT işlemlerini yapar.
"""

import threading
import time
from pathlib import Path

from app.core.audio_recorder import RecordingResult
from app.core.transcription.base_provider import BaseTranscriptionProvider
from app.core.transcription.models import TranscriptionResult
from app.core.transcription.models import TranscriptionResult
from app.services.config_manager import ConfigManager
from app.services.logger import get_logger
from app.core.exceptions import STTError, ModelLoadError

logger = get_logger(__name__)


class FasterWhisperProvider(BaseTranscriptionProvider):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(config_manager, parent)
        self._model = None
        self._shutting_down = False
        
        # Sadece 1 thread'in ayni anda islem yapmasini garanti altina alan kilit
        # Shutdown gibi main-thread islevlerinin ayni kilidi tekrar alabilmesi (re-entrant) icin RLock.
        self._lock = threading.RLock()

    def transcribe(self, recording: RecordingResult, op_id: int) -> None:
        """Asenkron transcription baslatir."""
        if self._shutting_down:
            return
            
        # Worker thread baslatiliyor (UI thread bloklanmamasi icin)
        t = threading.Thread(
            target=self._transcribe_worker,
            args=(recording, op_id),
            daemon=True,
            name="STTWorkerThread"
        )
        t.start()

    def _transcribe_worker(self, recording: RecordingResult, op_id: int) -> None:
        """Background thread icinde calisan ana is akisi."""
        with self._lock:
            if self._shutting_down:
                return
                
            start_time = time.time()
            
            # 1. Model yukleme / Kontrol
            if not self._is_loaded or self._model is None:
                if not self._load_model(op_id=op_id):
                    # Hata durumlari _load_model icinde sinyal olarak yayilir
                    return
            
            if self._shutting_down: return

            retry_on_cpu = False
            try:
                self._run_transcription(recording, start_time, op_id)
            except Exception as e:
                error_msg = str(e).lower()
                # Eger cuda/cublas vb kütüphane hatalariysa CPU fallback yapmayi dene (max 1 kez)
                # Veya eger out of memory ise
                if "cublas" in error_msg or "cudnn" in error_msg or "cuda" in error_msg or "memory" in error_msg:
                    logger.warning(f"Inference sirasinda CUDA hatasi tespit edildi: {e}")
                    logger.warning("CPU fallback tetikleniyor (int8)...")
                    retry_on_cpu = True
                else:
                    stt_err = STTError(f"Transcription sirasinda motor hata verdi: {e}")
                    stt_err.__cause__ = e
                    logger.error(str(stt_err), exc_info=True)
                    self.transcription_error.emit(str(stt_err), op_id)
            
            if retry_on_cpu and not self._shutting_down:
                # Modeli temizle
                self._model = None
                self._is_loaded = False
                
                # CPU fallback ile yeniden dene (1 kez)
                if self._load_model(op_id=op_id, override_device="cpu", override_compute="int8"):
                    try:
                        self._run_transcription(recording, start_time, op_id)
                    except Exception as e:
                        stt_err = STTError(f"CPU Fallback sonrasi transcription hatasi: {e}")
                        stt_err.__cause__ = e
                        logger.error(str(stt_err), exc_info=True)
                        self.transcription_error.emit(str(stt_err), op_id)

    def _run_transcription(self, recording: RecordingResult, start_time: float, op_id: int) -> None:
        """Asil transcription islemini gerceklestirir."""
        if self._shutting_down: return
        logger.info(f"Transcription basladi: {recording.path.name} (op_id={op_id})")
        
        cfg = self._config.config.stt.faster_whisper
        language = cfg.language
        
        import soundfile as sf
        import numpy as np
        audio_data, sr = sf.read(str(recording.path), dtype='float32')
        
        # Eğer kaydedici 16kHz desteklemediği için yüksek frekansta kaydettiyse downsample yap
        if sr != 16000:
            logger.info(f"Yüksek frekanslı kayıt ({sr}Hz) 16000Hz'e resample ediliyor...")
            orig_times = np.arange(len(audio_data)) / sr
            new_times = np.arange(int(len(audio_data) * 16000 / sr)) / 16000.0
            audio_data = np.interp(new_times, orig_times, audio_data).astype(np.float32)
            sr = 16000
        
        if self._shutting_down: return
        
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        
        # Prepare VAD parameters
        vad_params = None
        if cfg.vad_filter:
            vad_params = dict(
                threshold=cfg.vad_parameters.threshold,
                min_speech_duration_ms=cfg.vad_parameters.min_speech_duration_ms,
                min_silence_duration_ms=cfg.vad_parameters.min_silence_duration_ms,
                speech_pad_ms=cfg.vad_parameters.speech_pad_ms
            )
        
        logger.info(f"[STT Diagnostics] audio_duration={recording.duration_seconds:.2f}s, configured_language={language}, vad_filter={cfg.vad_filter}, vad_params={vad_params}")
        
        segments_gen, info = self._model.transcribe(
            audio_data,
            language=language,
            task="transcribe",
            vad_filter=cfg.vad_filter,
            vad_parameters=vad_params,
            condition_on_previous_text=False, # Prevent hallucination across separate short recordings
            beam_size=5
        )

        if self._shutting_down: return

        text_parts = []
        seg_count = 0
        
        logger.info(f"[STT Diagnostics] detected_language={info.language}, language_probability={info.language_probability:.4f}")

        for segment in segments_gen:
            if self._shutting_down: return
            text_parts.append(segment.text.strip())
            seg_count += 1
            logger.info(f"[STT Diagnostics] Segment {seg_count}: start={segment.start:.2f}s, end={segment.end:.2f}s, no_speech_prob={segment.no_speech_prob:.4f}, avg_logprob={segment.avg_logprob:.4f}")
        
        final_text = " ".join(text_parts).strip()
        processing_time = time.time() - start_time
        
        if not final_text:
            logger.warning(f"Transcription bitti ancak bos metin uretildi. (Segment count: {seg_count})")
        else:
            logger.info(f"Transcription bitti ({processing_time:.2f}s, {seg_count} segment).")

        result = TranscriptionResult(
            text=final_text,
            language=info.language,
            language_probability=info.language_probability,
            duration_seconds=recording.duration_seconds,
            processing_time_seconds=processing_time,
            model_name=getattr(self, "_current_model_size", "unknown")
        )
        
        if not self._shutting_down:
            self.transcription_done.emit(result, op_id)


    def _load_model(self, op_id: int, override_device: str = None, override_compute: str = None) -> bool:
        """Modeli yukler ve CUDA/CPU fallback mantigini uygular."""
        if self._shutting_down: return False
        self.model_load_started.emit()
        
        try:
            # Python 3.14'te `av` paketi derlenemedigi icin numpy array gecerek kullaniyoruz.
            # Ancak faster_whisper import sirasinda `av` modulu ariyip cokmesini engellemek icin mock'luyoruz.
            import sys
            from unittest.mock import MagicMock
            if 'av' not in sys.modules:
                sys.modules['av'] = MagicMock()
                
            from faster_whisper import WhisperModel
            from app.core.runtime_profile_resolver import RuntimeProfileResolver
            
            cfg = self._config.config.stt.faster_whisper
            resolved_model, resolved_device, resolved_compute = RuntimeProfileResolver.resolve_profile(self._config)
            
            # Override mekanizması (Fallback vb. durumlar için)
            model_size = resolved_model
            device = override_device if override_device else resolved_device
            compute_type = override_compute if override_compute else resolved_compute
            
            logger.info(f"[Model] requested model = {model_size}")
            
            # Modelin inecegi dizin
            models_dir = str(self._config.app_dir / "models")
            logger.info(f"[Model] cache root = {models_dir}")
            
            import os
            cache_created = False
            if not os.path.exists(models_dir):
                os.makedirs(models_dir, exist_ok=True)
                cache_created = True
            logger.info(f"[Model] cache directory exists/created = {cache_created}")
            
            needs_download = True
            if os.path.exists(models_dir):
                for d in os.listdir(models_dir):
                    if model_size in d:
                        needs_download = False
                        break
            
            logger.info(f"[Model] local model found = {not needs_download}")
            
            if needs_download:
                logger.info(f"[Model] download starting")
                if hasattr(self, "parent") and self.parent():
                    try:
                        self.parent()._tray.notify(
                            "Voice Typer",
                            f"Model ({model_size}) ilk kullanım için indiriliyor. Lütfen bekleyin...",
                            duration_ms=8000
                        )
                    except Exception as e:
                        logger.debug(f"Tray notification failed: {e}")
                        
            logger.info(f"[Model] initialization starting")
            self._model = WhisperModel(
                model_size_or_path=model_size,
                device=device,
                compute_type=compute_type,
                download_root=models_dir
            )
            
            if needs_download:
                logger.info(f"[Model] download completed")
                
            self._current_model_size = model_size
            logger.info(f"[Model] initialization completed")
            logger.info(f"[Model] actual device = {device}")
            logger.info(f"[Model] actual compute type = {compute_type}")
            
        except Exception as e:
            self._is_loaded = False
            self._model = None
            
            # CTrans2 ve CUDA inisiyalizasyon hatalarini burada donustur
            ml_err = ModelLoadError(f"CUDA/CTranslate2 baslatilamadi (Device={device}, Compute={compute_type}): {e}")
            
            logger.warning(str(ml_err))
            logger.warning("CPU fallback uygulaniyor (int8)...")
            try:
                self._model = WhisperModel(
                    model_size_or_path=model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=models_dir
                )
                logger.info(f"[Model] CPU fallback ile yuklendi.")
                logger.info(f"[Model] actual device = cpu")
                logger.info(f"[Model] actual compute type = int8")
            except Exception as cpu_e:
                final_err = ModelLoadError(f"Model ne GPU ne de CPU ile yuklenebildi. Hata: {cpu_e}")
                
                # Chain the exceptions manually for the logger, or raise and catch
                try:
                    raise final_err from ml_err
                except ModelLoadError as raised_err:
                    logger.exception("Model yukleme tamamen basarisiz oldu")
                    
                self.model_load_finished.emit(False, str(final_err))
                self.transcription_error.emit(str(final_err), op_id)
                return False

        self._is_loaded = True
        self.model_load_finished.emit(True, "")
        return True

    def shutdown(self) -> None:
        logger.info("STT Provider shutdown istendi...")
        self._shutting_down = True
        
        # Lock'i bekle (timeout = 2 saniye)
        if self._lock.acquire(timeout=2.0):
            try:
                self.unload_model()
                logger.info("STT Provider basariyla kapatildi.")
            finally:
                self._lock.release()
        else:
            logger.warning("STT Provider worker timeout oldu, lock alinamadi. Zorla terk ediliyor.")

    def unload_model(self) -> None:
        """Modeli bellekten kaldirir (ornek: ayarlar degistiginde lazy-load icin)."""
        with self._lock:
            self._model = None
            self._is_loaded = False

