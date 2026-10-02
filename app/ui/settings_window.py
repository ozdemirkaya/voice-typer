"""
app/ui/settings_window.py
=========================
Uygulama ayarlarini gosteren UI penceresi.
"""

import sounddevice as sd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, 
    QCheckBox, QPushButton, QTabWidget, QWidget, QFormLayout, QMessageBox,
    QSpinBox, QGroupBox
)
from PySide6.QtCore import Qt

from app.services.config_manager import ConfigManager
from app.services.logger import get_logger

logger = get_logger(__name__)

class SettingsWindow(QDialog):
    _instance = None

    @classmethod
    def show_window(cls, config_manager: ConfigManager, app_controller, parent=None):
        if cls._instance is None:
            cls._instance = cls(config_manager, app_controller, parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()

    def __init__(self, config_manager: ConfigManager, app_controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Typer - Ayarlar")
        self.resize(400, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._config_manager = config_manager
        self._app_controller = app_controller

        self._setup_ui()
        self._load_config()

    def closeEvent(self, event):
        SettingsWindow._instance = None
        super().closeEvent(event)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # -------------------------------------------------------------
        # Tab 1: Genel
        # -------------------------------------------------------------
        tab_general = QWidget()
        layout_general = QFormLayout(tab_general)

        self.edit_hotkey = QLineEdit()
        self.edit_hotkey.setPlaceholderText("Örn: alt+x")
        layout_general.addRow("Global Kısayol:", self.edit_hotkey)

        self.combo_lang = QComboBox()
        self.combo_lang.addItem("Türkçe", "tr")
        layout_general.addRow("Dil:", self.combo_lang)
        
        self.check_startup = QCheckBox("Windows açılışında otomatik başlat")
        layout_general.addRow("", self.check_startup)

        tabs.addTab(tab_general, "Genel")

        # -------------------------------------------------------------
        # Tab 2: Mikrofon
        # -------------------------------------------------------------
        tab_mic = QWidget()
        layout_mic = QVBoxLayout(tab_mic)

        form_mic = QFormLayout()
        
        box_mic = QHBoxLayout()
        self.combo_mic = QComboBox()
        self.btn_refresh_mic = QPushButton("Yenile")
        self.btn_refresh_mic.clicked.connect(self._populate_microphones)
        box_mic.addWidget(self.combo_mic, 1)
        box_mic.addWidget(self.btn_refresh_mic)
        
        form_mic.addRow("Giriş Cihazı:", box_mic)
        layout_mic.addLayout(form_mic)
        layout_mic.addStretch()

        tabs.addTab(tab_mic, "Mikrofon")

        # -------------------------------------------------------------
        # Tab 3: Speech-to-Text
        # -------------------------------------------------------------
        tab_stt = QWidget()
        layout_stt = QFormLayout(tab_stt)

        self.combo_model = QComboBox()
        self.combo_model.addItem("Small", "small")
        self.combo_model.addItem("Medium", "medium")
        self.combo_model.addItem("Large V3 Turbo", "large-v3-turbo")
        layout_stt.addRow("Model:", self.combo_model)

        self.combo_device = QComboBox()
        self.combo_device.addItem("Otomatik", "auto")
        self.combo_device.addItem("CPU", "cpu")
        self.combo_device.addItem("NVIDIA GPU (CUDA)", "cuda")
        layout_stt.addRow("Cihaz:", self.combo_device)

        self.combo_compute = QComboBox()
        self.combo_compute.addItem("Otomatik", "auto")
        self.combo_compute.addItem("Int8 (Düşük RAM)", "int8")
        self.combo_compute.addItem("Float16 (Hızlı GPU)", "float16")
        layout_stt.addRow("Hesaplama Tipi:", self.combo_compute)

        self.check_vad = QCheckBox("VAD (Boşlukları atla)")
        layout_stt.addRow("", self.check_vad)
        
        lbl_info = QLabel("<i>Model değişirse, bir sonraki kullanımda indirilir.</i>")
        layout_stt.addRow(lbl_info)

        tabs.addTab(tab_stt, "STT")

        # -------------------------------------------------------------
        # Tab 4: Davranış
        # -------------------------------------------------------------
        tab_behavior = QWidget()
        layout_behavior = QFormLayout(tab_behavior)

        self.spin_paste_delay = QSpinBox()
        self.spin_paste_delay.setRange(50, 2000)
        self.spin_paste_delay.setSuffix(" ms")
        layout_behavior.addRow("Yapıştırma Gecikmesi:", self.spin_paste_delay)

        self.check_keep_recordings = QCheckBox("Geçici ses dosyalarını sakla")
        layout_behavior.addRow("", self.check_keep_recordings)

        tabs.addTab(tab_behavior, "Davranış")

        # -------------------------------------------------------------
        # Buttons
        # -------------------------------------------------------------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Kaydet")
        btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(btn_save)

        main_layout.addLayout(btn_layout)

    def _populate_microphones(self, select_idx=None):
        self.combo_mic.clear()
        self.combo_mic.addItem("Sistem Varsayılanı", None)
        try:
            devices = sd.query_devices()
            target_combo_index = 0
            
            for idx, d in enumerate(devices):
                if d['max_input_channels'] > 0:
                    self.combo_mic.addItem(d['name'], idx)
                    if select_idx is not None and select_idx == idx:
                        target_combo_index = self.combo_mic.count() - 1
            
            if select_idx is not None:
                self.combo_mic.setCurrentIndex(target_combo_index)
                
        except Exception as e:
            logger.error(f"Mikrofon listesi alinamadi: {e}")

    def _load_config(self):
        cfg = self._config_manager.config
        
        # General
        mods = "+".join(cfg.hotkey.modifiers)
        hk = f"{mods}+{cfg.hotkey.key}" if mods else cfg.hotkey.key
        self.edit_hotkey.setText(hk)
        self.check_startup.setChecked(cfg.general.run_on_startup)
        
        # Audio
        self._populate_microphones(cfg.audio.device_index)
        
        # STT
        stt = cfg.stt.faster_whisper
        
        idx = self.combo_model.findData(stt.model_size)
        if idx >= 0: self.combo_model.setCurrentIndex(idx)
            
        idx = self.combo_device.findData(stt.device)
        if idx >= 0: self.combo_device.setCurrentIndex(idx)
            
        idx = self.combo_compute.findData(stt.compute_type)
        if idx >= 0: self.combo_compute.setCurrentIndex(idx)
            
        self.check_vad.setChecked(stt.vad_filter)
        
        # Behavior
        self.spin_paste_delay.setValue(cfg.text_injection.paste_delay_ms)
        self.check_keep_recordings.setChecked(cfg.audio.keep_recordings)

    def _save_settings(self):
        import copy
        cfg = self._config_manager.config
        old_cfg = copy.deepcopy(cfg)
        
        # Hotkey parsing
        hk_text = self.edit_hotkey.text().strip().lower()
        parts = hk_text.split('+')
        key = parts[-1] if parts else ""
        mods = parts[:-1]
        
        if not key:
            QMessageBox.warning(self, "Hata", "Geçersiz kısayol formatı.")
            return

        # 2. Runtime degisikliklerini uygula (Hotkey)
        hotkey_changed = (old_cfg.hotkey.key != key or old_cfg.hotkey.modifiers != mods)
        if hotkey_changed and self._app_controller._hotkey_manager:
            if not self._app_controller._hotkey_manager.change_hotkey(mods, key):
                QMessageBox.warning(self, "Hata", "Bu klavye kısayolu başka bir uygulama tarafından kullanılıyor veya geçersiz.\n\nEski kısayol korunacak.")
                return

        # Diger degerleri topla ve in-place guncelle
        cfg.hotkey.key = key
        cfg.hotkey.modifiers = mods
        
        cfg.audio.device_index = self.combo_mic.currentData()
        
        cfg.stt.faster_whisper.model_size = self.combo_model.currentData()
        cfg.stt.faster_whisper.device = self.combo_device.currentData()
        cfg.stt.faster_whisper.compute_type = self.combo_compute.currentData()
        cfg.stt.faster_whisper.vad_filter = self.check_vad.isChecked()
        
        cfg.text_injection.paste_delay_ms = self.spin_paste_delay.value()
        cfg.audio.keep_recordings = self.check_keep_recordings.isChecked()
        cfg.general.run_on_startup = self.check_startup.isChecked()
        
        # 3. Startup Registry guncelle (Atomic degil, basarisiz olursa loglar)
        from app.services import startup_manager
        startup_manager.sync_with_config(cfg.general.run_on_startup)
        
        # 4. Config'i kaydet (Atomic denemesi)
        try:
            self._config_manager.save()
        except Exception as e:
            # Dosyaya yazma basarisiz olursa rollback
            cfg.hotkey.key = old_cfg.hotkey.key
            cfg.hotkey.modifiers = old_cfg.hotkey.modifiers
            cfg.audio.device_index = old_cfg.audio.device_index
            cfg.stt.faster_whisper.model_size = old_cfg.stt.faster_whisper.model_size
            cfg.stt.faster_whisper.device = old_cfg.stt.faster_whisper.device
            cfg.stt.faster_whisper.compute_type = old_cfg.stt.faster_whisper.compute_type
            cfg.stt.faster_whisper.vad_filter = old_cfg.stt.faster_whisper.vad_filter
            cfg.text_injection.paste_delay_ms = old_cfg.text_injection.paste_delay_ms
            cfg.audio.keep_recordings = old_cfg.audio.keep_recordings
            cfg.general.run_on_startup = old_cfg.general.run_on_startup
            
            if hotkey_changed and self._app_controller._hotkey_manager:
                self._app_controller._hotkey_manager.change_hotkey(old_cfg.hotkey.modifiers, old_cfg.hotkey.key)
            QMessageBox.critical(self, "Hata", f"Ayarlar dosyaya kaydedilemedi:\n{e}")
            return
            
        # 4. Basarili. STT Unload kontrolu
        # model, device veya compute_type degistiyse unload yap. VAD degisiminde yapma.
        stt_old = old_cfg.stt.faster_whisper
        stt_new = cfg.stt.faster_whisper
        if (stt_old.model_size != stt_new.model_size or 
            stt_old.device != stt_new.device or 
            stt_old.compute_type != stt_new.compute_type):
            
            stt_provider = self._app_controller._stt_provider
            if stt_provider and hasattr(stt_provider, 'unload_model'):
                stt_provider.unload_model()
        
        logger.info("Ayarlar basariyla kaydedildi.")
        self.accept()

