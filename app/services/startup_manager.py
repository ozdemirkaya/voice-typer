"""
app/services/startup_manager.py
=================================
Windows Kayıt Defteri (Registry) üzerinden uygulamanın bilgisayar açılışında
otomatik başlatılmasını yönetir.

Sadece PyInstaller ile paketlenmiş (frozen) durumlarda aktif olur.
Development ortamındaki (python main.py) yollar registry'ye eklenmez.
"""
import sys
import os
import winreg
from pathlib import Path
from typing import Optional

from app.services.logger import get_logger

logger = get_logger(__name__)

# HKCU\Software\Microsoft\Windows\CurrentVersion\Run
_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_KEY_NAME = "VoiceTyper"

def is_frozen() -> bool:
    """Uygulamanın PyInstaller ile paketlenip paketlenmediğini döndürür."""
    return getattr(sys, "frozen", False)

def get_executable_path() -> Optional[str]:
    """Paketlenmiş uygulamanın tam yolunu döndürür."""
    if is_frozen():
        return sys.executable
    return None

def is_startup_enabled() -> bool:
    """Windows açılışında başlatma durumunu Registry'den okur."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _APP_KEY_NAME)
            
            exe_path = get_executable_path()
            if exe_path:
                # Value matches our executable exactly (with quotes)
                expected_value = f'"{exe_path}"'
                return value == expected_value
            return False
    except OSError:
        # Key bulunamadı veya değer yok
        return False

def enable_startup() -> bool:
    """Uygulamayı Windows açılışında başlatılacak şekilde kaydeder."""
    exe_path = get_executable_path()
    if not exe_path:
        logger.warning("Startup manager: Development modunda registry'ye kayıt yapılmaz.")
        return False
        
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
            # Boşluk içeren yollar için tırnak içine al
            winreg.SetValueEx(key, _APP_KEY_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        logger.info(f"Startup registry kaydı oluşturuldu: {exe_path}")
        return True
    except OSError as e:
        logger.error(f"Startup registry kaydı oluşturulamadı: {e}")
        return False

def disable_startup() -> bool:
    """Uygulamanın Windows açılışında başlatılmasını iptal eder."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, _APP_KEY_NAME)
        logger.info("Startup registry kaydı silindi.")
        return True
    except FileNotFoundError:
        # Zaten yok
        return True
    except OSError as e:
        logger.error(f"Startup registry kaydı silinemedi: {e}")
        return False

def sync_with_config(run_on_startup: bool) -> None:
    """Config değerine göre startup durumunu eşitler."""
    if not is_frozen():
        return
        
    currently_enabled = is_startup_enabled()
    if run_on_startup and not currently_enabled:
        enable_startup()
    elif not run_on_startup and currently_enabled:
        disable_startup()
