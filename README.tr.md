# Voice Typer

[Türkçe] | [English](README.md)

Voice Typer, global hotkey aracılığıyla ses kaydeden, bu sesi faster-whisper kullanarak yerel olarak (local) metne döken ve sonucu kayıt başladığında aktif olan uygulamaya otomatik olarak yazan, gizlilik odaklı (local-first) bir Windows masaüstü speech-to-text (STT) uygulamasıdır.

Voice Typer, tüm transkripsiyon işlemlerini tamamen yerel olarak gerçekleştirir. Hiçbir cloud speech API kullanılmaz, bu sayede tam veri gizliliği sağlanır.

---

## 1. Genel Bakış (Overview)
Voice Typer, sistem tepsinizde (system tray) çalışır ve özelleştirilebilir bir global hotkey'i dinler. Tetiklendiğinde sesinizi kaydeder, bu sesi yüksek derecede optimize edilmiş yerel bir STT motorundan (CTranslate2 üzerinde çalışan `faster-whisper`) geçirir ve elde edilen metni native Win32 `SendInput` API'leri aracılığıyla doğrudan aktif pencerenize yazar.

## 2. Özellikler
- **Native Win32 Global Hotkey:** Odak (focus) kaybetmeden herhangi bir uygulamadan kaydı kontrol edin.
- **%100 Yerel Transkripsiyon:** Hızlı ve gizli offline speech-to-text için `faster-whisper` kullanır.
- **NVIDIA CUDA Hızlandırması:** Native GPU hızlandırması için CUDA/cuDNN runtime'ı ile paketlenmiştir (CPU fallback desteği mevcuttur).
- **Aktif Pencere Koruması (Active Window Protection):** Odak değiştiğinde yanlışlıkla metin enjeksiyonunu önlemek için kayıt sırasında foreground `HWND` değerini hafızada tutar.
- **Pano Geri Yükleme (Clipboard Restoration):** Otomatik `Ctrl+V` metin enjeksiyonu işlemi sırasında panonuzdaki (clipboard) mevcut içeriği güvenle korur ve geri yükler.
- **Lazy Model Loading:** Hugging Face modelleri yerel olarak önbelleğe alınır (cache) ve yalnızca ihtiyaç duyulduğunda RAM'e yüklenir.
- **Yapılandırılabilir Çıkarım (Configurable Inference):** Seçilebilir model boyutları (`large-v3-turbo`, `small` vb.), cihaz (`auto`, `cuda`, `cpu`) ve compute type seçenekleri (`float16`, `int8`).
- **Silero VAD Entegrasyonu:** Transkripsiyon öncesinde sessizliği ve arka plan gürültüsünü filtreler.
- **Sistem Tepsisi (System Tray) Entegrasyonu:** Ayarları ve uygulama yaşam döngüsünü yönetmek için hafif PySide6 GUI.
- **Tekil Çalışma Koruması (Single-Instance Protection):** Süreçler arası isimlendirilmiş Mutex, uygulamanın aynı anda birden fazla kez çalışmasını engeller.
- **Güvenli Kapanış (Cooperative Shutdown):** Çıkış sırasında aktif ses akışlarını ve transkripsiyon thread'lerini güvenli biçimde sonlandırır.
- **Veri Gizliliği Ayrımı:** Uygulama binary dosyaları ve kullanıcı verileri (`%LOCALAPPDATA%\VoiceTyper`) birbirinden kesin olarak ayrılmıştır.
- **Kullanıcı Bazlı Kurulum (Per-User Installer):** PyInstaller (onedir) ile paketlenmiştir ve düşük yetki (low-privilege) gerektiren Inno Setup installer aracılığıyla dağıtılır.

## 3. Demo / Ekran Görüntüleri

### Settings
![Voice Typer Settings](docs/assets/settings.png)

### System Tray
![Voice Typer System Tray](docs/assets/tray.png)

## 4. Nasıl Çalışır?
1. Kullanıcı global hotkey'e basar (örn. `Alt+X`).
2. Uygulama o an aktif olan pencere tutamacını (`HWND`) kaydeder ve WASAPI üzerinden ses kaydına başlar.
3. Kullanıcı kaydı durdurmak için kısayol tuşuna tekrar basar.
4. Ses 16 kHz'e normalize edilir (sürücü reddederse native fallback interpolasyonu ile) ve yerel `faster-whisper` motoruna iletilir.
5. Çıkarılan metin panoya (clipboard) kopyalanır.
6. Hedef `HWND`'ye sentetik bir `Ctrl+V` tuş basımı gönderilir.
7. Orijinal pano içeriği sorunsuz bir şekilde geri yüklenir.

## 5. Mimari (Architecture)
Voice Typer, yoğun transkripsiyon işlemleri sırasında GUI'nin donmasını (lockup) önlemek için asenkron event-driven bir mimariye dayanır.

```
Global Hotkey 
     ↓
AudioRecorder (WASAPI)
     ↓
WAV / 16 kHz normalization
     ↓
AppController (State Machine)
     ↓
FasterWhisperProvider (Worker Thread)
     ↓
CUDA or CPU (CTranslate2)
     ↓
Transcript
     ↓
ClipboardManager & TextInjector (Win32)
     ↓
Target Application
```

### Uygulama State Machine (Durum Makinesi)
Güvenilir çalışmayı sağlamak için uygulama katı state (durum) geçişleri uygular:
`IDLE` → `RECORDING` → `PROCESSING` → `LOADING_MODEL` → `PROCESSING` → `IDLE`

Yarış durumlarını (race conditions) önlemek için operation_id ve stale callback koruması uygulanmıştır (örneğin, bir transkripsiyonu yarıda kesip, önceki thread henüz sonlanmadan yeni bir kayıt başlatmak gibi).

## 6. Teknoloji Yığını (Tech Stack)
- **Python 3.14**
- **PySide6** (System Tray GUI & Threading)
- **faster-whisper & CTranslate2** (Speech-to-Text çıkarımı)
- **sounddevice & soundfile** (Ses yakalama)
- **pywin32** (Win32 API entegrasyonu)
- **PyInstaller** (Frozen executable paketleme)
- **Inno Setup** (Windows Kurulumu)

## 7. Kurulum (Installation)
Installer'ı kaynak koddan derleyebilir (bkz. [Installer'ın Derlenmesi](#15-installerın-derlenmesi-building-the-installer)) veya derlenmiş Setup executable dosyasını Releases sayfasından indirebilirsiniz.
Kurulum (installer) Administrator yetkileri **gerektirmez** ve doğrudan `%LOCALAPPDATA%\Programs\VoiceTyper` dizinine yüklenir.

## 8. Kullanım (Usage)
1. Başlat Menüsünden Voice Typer'ı çalıştırın.
2. Sistem tepsinizde bir mikrofon ikonu belirecektir.
3. Herhangi bir metin alanına (Not Defteri, Word, web tarayıcınız vb.) tıklayın.
4. Kaydı başlatmak için `Alt+X` (varsayılan global hotkey) tuşlarına basın.
5. Cümlenizi söyleyin.
6. `Alt+X` tuşlarına tekrar basın. Metin anında aktif pencerenize yazılacaktır.

## 9. Yapılandırma (Configuration)
Ayarlar `%LOCALAPPDATA%\VoiceTyper\config.json` dosyasında saklanır. Hotkey, mikrofon cihaz indeksi, sample rate ve model boyutu gibi parametreleri manuel olarak ayarlayabilirsiniz. Hatalı JSON dosyaları (malformed JSON) otomatik olarak yedeklenir ve varsayılan ayarlarla güvenli biçimde değiştirilir.

## 10. CPU / NVIDIA CUDA Desteği
Voice Typer, NVIDIA GPU'ları otomatik olarak algılar ve maksimum hız için `float16` CUDA inference kullanır. Uyumlu bir GPU bulunamazsa veya başlatma başarısız olursa, güvenli bir şekilde `int8` CPU inference (CPU fallback) moduna geçer.
CUDA/cuDNN DLL'leri çalışma zamanında `os.add_dll_directory` aracılığıyla dinamik olarak sürece dahil edilir (injected). Bu sayede host sistemin `PATH` değişkeni kirletilmemiş olur.

## 11. Gizlilik (Privacy)
- **%100 Yerel Çıkarım:** Transkripsiyon (Speech transcription) işlemi tamamen yerel olarak gerçekleştirilir.
- **Cloud API Yok:** Ses hiçbir zaman bulut tabanlı bir transcription API'sine gönderilmez.
- **Model İndirmeleri:** Model binary dosyaları, ihtiyaç duyulduğunda doğrudan Hugging Face Hub'dan (örn. `mobiuslabsgmbh/faster-whisper-large-v3-turbo`) indirilir ve yerel olarak önbelleğe alınır (cached).
- **Ses Verisi Saklanmaz (No Audio Retention):** Varsayılan olarak ses kayıtları işlendikten hemen sonra silinir. Diskte kalıcı olarak tutulmazlar.
- **Telemetri Yok:** Transkripsiyon (Transcript) içerikleri uygulama loglarına yazılmaz veya herhangi bir sunucuya gönderilmez.
- **İzole Edilmiş Veri:** Çalışma zamanı verileri (Runtime data) güvenli bir şekilde `%LOCALAPPDATA%\VoiceTyper` dizini altında saklanır.

## 12. Proje Yapısı (Project Structure)
```text
VoiceTyper/
├── app/
│   ├── core/           # STT, Audio, Clipboard, State Machine
│   ├── services/       # Config, Logger, CUDA runtime, Registry
│   └── ui/             # PySide6 Tray Icon
├── tests/              # Regression and Architecture Tests
├── docs/               # Documentation
├── main.py             # Application Entrypoint
├── requirements.txt    # Production Dependencies
├── voice_typer.spec    # PyInstaller Build Spec
├── installer.iss       # Inno Setup Script
└── README.md
```

## 13. Geliştirme Ortamı Kurulumu (Development Setup)
Windows üzerinde projeyi geliştirme ortamında kurmak için:

```powershell
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```
*(Alternatif olarak, projede sağlanan `setup.bat` ve `run.bat` scriptlerini kullanabilirsiniz).*

## 14. PyInstaller ile Derleme (Building with PyInstaller)
CUDA runtime'ı içeren taşınabilir (portable) bir `.exe` klasörü (onedir formatı) oluşturmak için:
```powershell
pyinstaller voice_typer.spec --noconfirm
```
Çıktı `dist\VoiceTyper` dizininde oluşturulacaktır.

## 15. Installer'ın Derlenmesi (Building the Installer)
Kullanıcı bazlı (per-user) Inno Setup installer oluşturmak için:
1. PyInstaller build işleminin tamamlandığından emin olun.
2. Inno Setup Compiler üzerinden `installer.iss` dosyasını açın.
3. **Compile** butonuna tıklayın.
Çıktı olan `VoiceTyperSetup.exe`, `installer\` dizininde oluşturulacaktır.

## 16. Testler (Testing)
Anlamlı mimari testler ve regresyon testleri `tests/` dizininde bulunur. Bunlar arasında state transition kontrolleri, shutdown simülasyonları ve config recovery (ayarları kurtarma) doğrulamaları yer alır.

## 17. Teknik Zorluklar / Mühendislik Notları
Windows için sorunsuz çalışan arka plan odaklı bir voice-typing aracı geliştirmek çeşitli mühendislik zorluklarını beraberinde getirdi:
- **Native Win32 RegisterHotKey Integration:** Bloklayıcı `RegisterHotKey` Win32 çağrılarını, Qt native event filtering (`installNativeEventFilter`) aracılığıyla asenkron `PySide6` event loop ile birleştirmek.
- **Bundled CUDA/cuDNN Runtime:** Devasa NVIDIA CUDA/cuDNN `.dll` dosyalarını, sistemin kalıcı `PATH` değişkenini bozmadan veya sistemi DLL hijacking riskine maruz bırakmadan PyInstaller frozen resource paths üzerinden paketlemek.
- **Asynchronous State Management:** Kullanıcı, ağır bir CTranslate2 worker thread'i tamamlanmadan arka arkaya hotkey'i tetiklediğinde, operation_id ve stale callback protection kullanarak yarış durumlarını (race conditions) önlemek.
- **Active HWND Protection:** Kayıt başladığı an foreground window tutamacını saklamak ve paste (yapıştırma) işleminden önce sıkı bir şekilde doğrulamak; böylece kullanıcı uygulama değiştirirse metnin asla yanlış pencereye yazılmamasını (inject edilmemesini) sağlamak.
- **Clipboard Restore:** Kullanıcının injection sırasında kopyalanmış verilerini kaybetmemesi için `CF_UNICODETEXT`, `CF_DIB` ve diğer clipboard formatları için best-effort bir yedekleme ve geri yükleme mekanizması uygulamak.
- **CUDA to CPU Fallback:** CUDA donanımı bulunamadığında veya başlatılamadığında model ağırlıklarını ve engine'i dinamik olarak CPU'ya devretmek (fallback).
- **Audio Processing:** Mikrofon frekanslarındaki uyuşmazlıkları çözmek için 16 kHz sample-rate normalization uygulamak.
- **Model & Assets Lifecycle:** Hugging Face model cache/download lifecycle'ı yönetmek ve Silero VAD ONNX modelini PyInstaller ile başarılı şekilde paketlemek.
- **Application Locks:** Uygulamanın birden fazla çalışmasını engellemek için single-instance mutex entegre etmek.
- **Cooperative Shutdown & RLock:** STT worker thread'inin sonlandırılması sırasında Qt Main Thread'i bloke eden ve deadlock'a sebep olan non-reentrant lock hatasını tespit edip, RLock deadlock fix uygulayarak güvenli kapanışı sağlamak.
- **Installation:** Kullanıcı bazlı (per-user Inno Setup installer) mimari tasarlayarak admin izinlerine gerek kalmadan izole edilmiş bir uygulama kurmak.

## 18. Bilinen Sınırlamalar (Known Limitations)
- **Yalnızca Windows (Windows Only):** Hotkey, clipboard ve input injection (girdi enjeksiyonu) işlemleri için büyük ölçüde Win32 API'lerine dayanır.
- **İlk Çalıştırmada İnternet Gereksinimi:** Uygulama, belirtilen modeli Hugging Face'den indirmek için ilk STT çalıştırması sırasında internet erişimine ihtiyaç duyar.
- **Donanım Gereksinimleri:** Büyük modeller (`large-v3-turbo` gibi) önemli ölçüde RAM/VRAM tüketir. Eski donanımlarda CPU inference kullanımı hafif gecikmelere (latency) yol açabilir.
- **Sample Rate Fallback:** Bir mikrofon 16 kHz WASAPI akışlarını reddederse, uygulama linear interpolation ile downsampling (`numpy.interp`) uygular. Bu durum küçük miktarda aliasing (örtüşme) oluşturabilir (fakat Whisper'ın akustik özellikleri için bu ihmal edilebilir bir durumdur).

## 19. Yol Haritası (Roadmap)
- Modelleri ve kısayol tuşlarını (hotkey) görsel olarak değiştirmeye olanak tanıyan GUI Ayarlarının genişletilmesi.
- Uzun süreli bekleme durumları (idle states) için bellek kullanımı (memory usage) optimizasyonu.
- Daha geniş çaplı mikrofon uyumluluk testleri.
- Testler ve build'ler için otomatik CI pipeline'larının uygulanması.

## 20. Güvenlik (Security)
Zafiyet bildirim kurallarımız için lütfen `SECURITY.md` dosyasını inceleyin. Ayrıca `SECURITY_AUDIT.md` dosyasında kapsamlı bir temel güvenlik denetimi (security audit) raporu mevcuttur.

## 21. Lisans (License)
Bu proje MIT Lisansı ile lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakabilirsiniz.
