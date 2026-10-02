"""
app/services/cuda_runtime.py
==============================
CUDA Runtime (cuBLAS, cuDNN) dizinlerini bulup Windows process ortamına
dinamik olarak ekleyen servis.

faster-whisper / CTranslate2 yüklenmeden ÖNCE import edilip initialize
edilmelidir. Sistem PATH değişkenini global olarak kalıcı şekilde bozmaz,
yalnızca aktif process (ve os.add_dll_directory ile mevcut thread) için 
DLL arama yollarına ekleme yapar.
"""
import os
import sys
from pathlib import Path
from typing import List

from app.services.logger import get_logger

logger = get_logger(__name__)

# DLL handle'larinin (add_dll_directory donuslerinin) scope bitince
# kaybolmamasi ve garbage collect edilmemesi icin global referans tutuyoruz.
_dll_directories = []

def _find_cuda_runtime_paths() -> List[Path]:
    """
    Sanal ortam içerisindeki (veya mevcut sys.path içerisindeki)
    'nvidia-cublas-cu12' ve 'nvidia-cudnn-cu12' klasörlerini bulur ve
    içlerindeki 'bin' dizinlerinin yollarını döndürür.
    Eğer uygulama PyInstaller ile paketlenmişse (frozen), 
    doğrudan bundle içindeki cuda_runtime klasörünü döndürür.
    """
    if getattr(sys, "frozen", False):
        # Frozen modda _MEIPASS veya executable dizinindeki '_internal/cuda_runtime' kullanılır.
        if hasattr(sys, "_MEIPASS"):
            bundle_dir = Path(sys._MEIPASS)
        else:
            bundle_dir = Path(sys.executable).parent / "_internal"
            
        cuda_dir = bundle_dir / "cuda_runtime"
        if cuda_dir.is_dir():
            logger.info(f"CUDA runtime source: {cuda_dir} (Bundled)")
            return [cuda_dir]
        else:
            logger.warning(f"CUDA runtime source: {cuda_dir} bulunamadı!")
            return []

    logger.info("CUDA runtime source: Python .venv (Development)")
    paths = []
    
    # sys.path genellikle .venv/Lib/site-packages'i icerir
    for site_pkg in sys.path:
        site_path = Path(site_pkg)
        if not site_path.is_dir():
            continue
            
        nvidia_path = site_path / "nvidia"
        if not nvidia_path.is_dir():
            continue
            
        # nvidia altindaki cublas ve cudnn klasorlerini ara
        for module in ["cublas", "cudnn", "cuda_nvrtc"]:
            bin_dir = nvidia_path / module / "bin"
            if bin_dir.is_dir():
                paths.append(bin_dir)
                
    return paths

def initialize_cuda_runtime() -> bool:
    """
    CUDA runtime DLL'lerini bulur ve process'in DLL arama yollarina ekler.
    Basarili olursa True, klasorler bulunamazsa False doner (CPU fallback icin).
    """
    global _dll_directories
    
    # 1. Zaten eklendiyse (veya Windows degilse) islem yapma
    if sys.platform != "win32":
        logger.debug("CUDA Runtime Bootstrapper sadece Windows'ta calisir.")
        return True
        
    if _dll_directories:
        logger.debug("CUDA Runtime zaten initialize edildi.")
        return True
        
    # 2. Dizinleri bul
    bin_paths = _find_cuda_runtime_paths()
    if not bin_paths:
        logger.warning("CUDA/cuDNN runtime dizinleri .venv icinde bulunamadi! GPU destegi saglanamayabilir.")
        return False
        
    # 3. Process ortamına (PATH ve add_dll_directory) ekle
    logger.info(f"CUDA/cuDNN runtime bulunarak ortama eklendi ({len(bin_paths)} dizin)")
    
    current_path = os.environ.get("PATH", "")
    new_paths = []
    
    for b_path in bin_paths:
        b_str = str(b_path)
        logger.debug(f"CUDA Dizin Eklendi: {b_str}")
        
        # os.add_dll_directory Windows 3.8+ ile resmi olarak desteklenen yontemdir
        try:
            handle = os.add_dll_directory(b_str)
            _dll_directories.append(handle)
        except Exception as e:
            logger.warning(f"os.add_dll_directory({b_str}) basarisiz: {e}")
            
        # Legacy uyumluluk ve alt process'ler (subprocess) icin PATH'e de ekliyoruz
        if b_str not in current_path:
            new_paths.append(b_str)
            
    if new_paths:
        os.environ["PATH"] = os.pathsep.join(new_paths) + os.pathsep + current_path
        
    is_frozen = getattr(sys, "frozen", False)
    cuda_dir_log = str(bin_paths[0]) if bin_paths else "None"
    
    logger.info(f"[CUDA] frozen = {is_frozen}")
    logger.info(f"[CUDA] runtime source = {'bundled' if is_frozen else 'venv'}")
    logger.info(f"[CUDA] dll directory = {cuda_dir_log}")
    logger.info(f"[CUDA] runtime available = True")
        
    return True

_cuda_available = None

def is_cuda_available() -> bool:
    global _cuda_available
    if _cuda_available is None:
        _cuda_available = initialize_cuda_runtime()
    return _cuda_available
