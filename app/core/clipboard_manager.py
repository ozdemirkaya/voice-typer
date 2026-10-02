"""
app/core/clipboard_manager.py
================================
Pano (Clipboard) işlemlerini güvenli ve best-effort yöneten modül.
"""

import time
import win32clipboard
from app.services.logger import get_logger
from app.core.exceptions import ClipboardError

logger = get_logger(__name__)

class ClipboardManager:
    def __init__(self):
        # Desteklenen ve geri yuklemeye calisacagimiz formatlar
        # 13: CF_UNICODETEXT, 1: CF_TEXT, 8: CF_DIB (Bitmap), 15: CF_HDROP (Dosya)
        self._target_formats = [13, 1, 8, 15]
        self._backup_data = {}

    def _open_clipboard_safe(self, retries=5, delay=0.05) -> bool:
        """Clipboard baska uygulama tarafindan kilitliyse birkac kez dener."""
        for attempt in range(retries):
            try:
                win32clipboard.OpenClipboard()
                return True
            except Exception as e:
                time.sleep(delay)
        logger.warning(f"Clipboard acilamadi ({retries} deneme sonrasi).")
        return False

    def backup(self) -> None:
        """Mevcut pano icerigini best-effort yedekler."""
        self._backup_data.clear()
        
        if not self._open_clipboard_safe():
            return
            
        try:
            available_formats = []
            f = win32clipboard.EnumClipboardFormats(0)
            while f:
                available_formats.append(f)
                f = win32clipboard.EnumClipboardFormats(f)
                
            for fmt in self._target_formats:
                if fmt in available_formats:
                    try:
                        # DIB gibi veriler buyuk olabilir, memory hatasi ihtimaline karsi try-except
                        data = win32clipboard.GetClipboardData(fmt)
                        self._backup_data[fmt] = data
                    except Exception as e:
                        logger.debug(f"Pano yedekleme hatasi (Format {fmt}): {e}")
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
                
        logger.debug(f"Pano yedeklendi. Yedeklenen formatlar: {list(self._backup_data.keys())}")

    def set_text(self, text: str) -> bool:
        """Pano icerigine yeni metin koyar."""
        if not self._open_clipboard_safe():
            return False
            
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            logger.debug("Pano icerigi guncellendi (CF_UNICODETEXT).")
            return True
        except Exception as e:
            err = ClipboardError(f"Panoya yazi yazilamadi: {e}")
            try:
                raise err from e
            except ClipboardError as raised_err:
                logger.error("Pano set_text basarisiz oldu", exc_info=raised_err)
            return False
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

    def restore(self) -> None:
        """Yedeklenen veriyi panoya geri yukler (best-effort)."""
        if not self._backup_data:
            return
            
        if not self._open_clipboard_safe():
            return
            
        try:
            win32clipboard.EmptyClipboard()
            for fmt, data in self._backup_data.items():
                try:
                    win32clipboard.SetClipboardData(fmt, data)
                except Exception as e:
                    logger.debug(f"Pano geri yukleme hatasi (Format {fmt}): {e}")
            logger.debug("Pano yedekten geri yuklendi.")
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
