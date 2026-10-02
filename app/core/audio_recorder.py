"""
app/core/audio_recorder.py
===========================
Ses kaydı altyapısı (Phase 4).

Sorumluluklar:
- PortAudio/sounddevice ile mikrofon üzerinden ses kaydı.
- sounddevice callback'inden asenkron (Thread-safe) olarak WAV dosyasına yazma.
- UI thread'ini asla bloklamama.
- Kısa/kazara basılan kayıtları (threshold) tespit etme.
- Sonuçları RecordingResult sınıfı ile AppController'a iletme.

Thread Mimarisi:
1. UI Thread: start(), stop() çağrılarını yapar.
2. PortAudio Thread: _audio_callback() metodunu çağırır. Sadece queue.put() yapar.
3. Writer Thread: Queue'dan gelen NumPy dizilerini soundfile ile diske yazar.
                  Kayıt bittiğinde dosyayı kapatıp recording_stopped sinyalini tetikler.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal

from app.services.config_manager import ConfigManager
from app.services.logger import get_logger
from app.core.exceptions import AudioError

logger = get_logger(__name__)


@dataclass
class RecordingResult:
    """Kayıt işlemi sonucunu temsil eden typed data class."""
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    # Kazara/kısa basma koruması (duration < threshold ise False)
    is_valid: bool


class AudioRecorder(QObject):
    """
    Asenkron ses kayıt yöneticisi.
    AppController sadece start/stop çağırır ve sinyalleri dinler.
    """

    # Başarılı şekilde kayıt başladığında
    recording_started = Signal()
    
    # Kayıt bitip WAV dosyası diske güvenle yazıldığında (result, op_id)
    recording_stopped = Signal(object, int)  # type: RecordingResult, int
    
    # İzin, mikrofon yokluğu vb. hatalarda
    recording_failed = Signal(str, int)

    def __init__(self, config_manager: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config_manager
        
        # Temp ve Saved audio dosyalarının kaydedileceği klasör
        self._temp_dir = self._config.app_dir / "cache" / "audio" / "temp"
        self._saved_dir = self._config.app_dir / "cache" / "audio" / "saved"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._saved_dir.mkdir(parents=True, exist_ok=True)
        
        self._cleanup_old_temp_files()
        
        # State değişkenleri
        self._is_recording: bool = False
        self._stream: sd.InputStream | None = None
        self._writer_thread: threading.Thread | None = None
        
        # Audio iletişim kuyruğu (PortAudio callback -> Writer thread)
        self._audio_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        
        # Metadata takibi
        self._start_time: float = 0.0
        self._current_file: Path | None = None
        self._current_op_id: int = 0

    def _cleanup_old_temp_files(self) -> None:
        """Startup sirasinda 24 saatten eski ve temp klasorunde kalmis .wav dosyalarini temizler."""
        if self._config.config.audio.keep_recordings:
            # Kullanicinin isteyerek kaydettigi seylere dokunma, temp temizligi sadece keep_recordings=False ise guvenli
            pass
            
        try:
            now = time.time()
            for wav_file in self._temp_dir.glob("*.wav"):
                if wav_file.is_file():
                    age_seconds = now - wav_file.stat().st_ctime
                    if age_seconds > 24 * 3600:
                        try:
                            wav_file.unlink()
                            logger.debug(f"Eski temp dosyasi silindi: {wav_file.name}")
                        except Exception as e:
                            logger.warning(f"Eski temp dosyasi silinemedi: {e}")
        except Exception as e:
            logger.error(f"Temp cleanup hatasi: {e}")

    @property
    def is_recording(self) -> bool:
        """Kayıt işlemi devam ediyor mu?"""
        return self._is_recording

    def get_input_devices(self) -> list[dict]:
        """Sistemdeki mevcut input cihazlarını döndürür."""
        devices = []
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev['max_input_channels'] > 0:
                    devices.append({'id': idx, 'name': dev['name']})
        except Exception as e:
            logger.error(f"Cihaz listesi alınamadı: {e}")
        return devices

    def start(self, op_id: int, device_id: Optional[int] = None) -> bool:
        """
        Kayıt işlemini başlatır.
        device_id None ise varsayılan Windows input cihazını dener.
        Hata olursa recording_failed sinyali yayılır ve False döner.
        """
        if self._is_recording:
            logger.warning("AudioRecorder zaten kayıt yapıyor.")
            return False

        self._current_op_id = op_id

        cfg = self._config.config.audio
        target_device = device_id if device_id is not None else cfg.device_index
        sample_rate = cfg.sample_rate
        channels = cfg.channels

        # Whisper STT modelleri STRICTLY 16000 Hz ses bekler.
        # sounddevice (WASAPI/DirectSound) arka planda otomatik resampling yapar,
        # bu nedenle cihazın varsayılan oranını kullanmak yerine direkt 16000 istiyoruz.
        if sample_rate == 0:
            sample_rate = 16000

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = self._saved_dir if self._config.config.audio.keep_recordings else self._temp_dir
        self._current_file = target_dir / f"recording_{timestamp}.wav"

        # Kuyruğu temizle
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

        try:
            # 1. Ses akışını aç
            try:
                self._stream = sd.InputStream(
                    samplerate=sample_rate,
                    device=target_device,
                    channels=channels,
                    dtype='float32',
                    callback=self._audio_callback
                )
            except Exception as e:
                # 16000 Hz desteklenmiyorsa cihazın native oranına fallback yap
                logger.warning(f"16000 Hz desteklenmiyor olabilir ({e}). Native değere dönülüyor...")
                dev_info = sd.query_devices(target_device, 'input')
                sample_rate = int(dev_info['default_samplerate'])
                self._stream = sd.InputStream(
                    samplerate=sample_rate,
                    device=target_device,
                    channels=channels,
                    dtype='float32',
                    callback=self._audio_callback
                )
                logger.info(f"Native sample rate kullanılıyor: {sample_rate} Hz")

            
            # 2. Diske yazıcı thread'i başlat (op_id ile)
            self._writer_thread = threading.Thread(
                target=self._writer_worker,
                args=(self._current_file, sample_rate, channels, self._current_op_id),
                daemon=True,
                name="AudioWriterThread"
            )
            self._writer_thread.start()

            # 3. Akışı başlat
            self._stream.start()
            self._start_time = time.time()
            self._is_recording = True
            
            logger.info(f"Kayıt başladı: {self._current_file.name} "
                        f"({sample_rate}Hz, {channels}ch, Device={target_device})")
            self.recording_started.emit()
            return True

        except Exception as e:
            audio_err = AudioError(f"Kayıt başlatılamadı: {e}")
            try:
                raise audio_err from e
            except AudioError as raised_err:
                logger.error("AudioRecorder baslatilamadi", exc_info=raised_err)
                
            self._cleanup()
            # Kullanıcı dostu hata mesajı (örneğin mikrofon yetkisi veya cihaz yok)
            self.recording_failed.emit(
                "Mikrofon başlatılamadı.\n"
                "Lütfen Ayarlar'dan geçerli bir cihaz seçtiğinize ve "
                "Windows Gizlilik ayarlarından mikrofon erişimi verdiğinize emin olun.",
                op_id
            )
            return False
    def stop(self) -> None:
        """
        Kayıt işlemini durdurur. Shutdown sırasında timeout'lu beklenmez cunku UI thread'dir.
        Sadece stream'i stop eder ve kuyruga None atar.
        """
        if not self._is_recording:
            return

        logger.debug("Kayıt durduruluyor...")
        self._is_recording = False
        
        # InputStream'i durdur (callback'in çağrılması kesilir)
        if self._stream:
            try:
                self._stream.stop()
            except Exception as e:
                logger.warning(f"InputStream stop edilirken hata: {e}")

        # Kuyruğa None atarak writer thread'in kapanmasını sağla
        self._audio_queue.put(None)
        
        # Writer thread kendi içinde recording_stopped sinyalini yayacak.
        # Böylece UI thread diske yazma işlemi (buffer boşaltma) sırasında bloklanmaz.

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        """
        PortAudio thread'inde her buffer dolduğunda çağrılır.
        YALNIZCA KOPYALAMA VE KUYRUĞA EKLEME YAPMALIDIR. AĞIR İŞLEM YASAK.
        """
        if status:
            logger.warning(f"Audio callback durumu: {status}")
            
        # indata read-only olduğu için kopyasını oluşturup thread-safe kuyruğa gönder
        self._audio_queue.put(indata.copy())

    def _writer_worker(self, filepath: Path, sample_rate: int, channels: int, op_id: int) -> None:
        """
        Background Thread: Kuyruktan gelen ses paketlerini alır ve WAV dosyasına yazar.
        Kuyruğa 'None' eklendiğinde dosyayı kapatır ve sinyali yayar.
        """
        try:
            # SoundFile'ı oluştur
            with sf.SoundFile(str(filepath), mode='w', samplerate=sample_rate, channels=channels) as file:
                while True:
                    data = self._audio_queue.get()
                    if data is None:
                        # Stop komutu geldi, döngüden çık
                        break
                    file.write(data)
            
            # Kayıt başarıyla kaydedildi, süreyi hesapla
            duration = time.time() - self._start_time
            logger.info(f"WAV diske yazıldı: {filepath.name} (Süre: {duration:.2f}s)")
            
            # Çok kısa kayıtları (kazara basma) tespit et
            min_dur_ms = self._config.config.audio.min_duration_ms
            is_valid = duration >= (min_dur_ms / 1000.0)
            
            if not is_valid:
                logger.warning(f"Kayıt iptal edildi: Süre {duration*1000:.0f}ms < {min_dur_ms}ms (Kazara basma tespit edildi)")

            # Sonuç objesi oluştur
            result = RecordingResult(
                path=filepath,
                duration_seconds=duration,
                sample_rate=sample_rate,
                channels=channels,
                is_valid=is_valid
            )
            
            # Signal emit thread-safe'dir (Qt queued connection kullanır)
            self.recording_stopped.emit(result, op_id)

        except Exception as e:
            audio_err = AudioError(f"Writer thread hatası (diske yazılırken çöktü): {e}")
            try:
                raise audio_err from e
            except AudioError as raised_err:
                logger.error("Ses dosyasina yazi yazilamadi", exc_info=raised_err)
            self.recording_failed.emit(f"Ses dosyasına yazılırken sistem hatası oluştu: {e}", op_id)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """İç kaynakları güvenle temizler. (PortAudio stream ve referanslar)"""
        self._is_recording = False
        if self._stream:
            try:
                self._stream.close()
            except Exception as e:
                logger.warning(f"Stream kapatilirken hata olustu: {e}")
        self._stream = None
        self._writer_thread = None
