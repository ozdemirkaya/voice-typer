"""
app/services/logger.py
======================
Merkezi loglama yapılandırması.

Kullanım:
    from app.services.logger import setup_logging, get_logger

    # main.py'de bir kez çağrılır:
    setup_logging(log_level="INFO", log_dir=Path("logs"))

    # Her modülde:
    logger = get_logger(__name__)
    logger.info("Mesaj")
"""

import logging
import logging.handlers
from pathlib import Path


# Log formatı: tarih saat [SEVİYE  ] modül: mesaj
_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)-30s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Tüm uygulama logları bu root logger altında toplanır.
_ROOT_LOGGER_NAME = "voicetyper"


def setup_logging(log_level: str = "INFO", log_dir: Path | None = None) -> None:
    """
    Uygulama genelinde loglama yapılandırmasını başlatır.

    Bu fonksiyon yalnızca bir kez (main.py'de) çağrılmalıdır.

    Args:
        log_level: Dosyaya yazılacak minimum log seviyesi.
                   "DEBUG" | "INFO" | "WARNING" | "ERROR"
                   Konsola her zaman DEBUG+ yazılır (geliştirme için).
        log_dir:   Log dosyasının oluşturulacağı klasör.
                   None verilirse dosya yazılmaz, sadece konsola yazılır.
    """
    level = _parse_level(log_level)

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(logging.DEBUG)  # Handler'lar kendi seviyesini filtreler
    root.handlers.clear()         # Çift kayıt önleme (reload durumunda)
    root.propagate = False        # Root Python logger'a taşmayı engelle

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Konsol handler (geliştirme/debug için her zaman aktif) ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # --- Rotating file handler ---
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "voicetyper.log"

            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=5 * 1024 * 1024,   # 5 MB per file
                backupCount=3,               # voicetyper.log.1, .2, .3
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

            # Log başlangıcını dosyaya da yaz
            root.info(f"Log dosyası: {log_file}")
        except OSError as exc:
            root.warning(f"Log dosyası oluşturulamadı ({log_dir}): {exc}")


def get_logger(name: str) -> logging.Logger:
    """
    'voicetyper' namespace altında bir logger döndürür.

    Args:
        name: Genellikle __name__ geçilir.
              Örnek: 'app.services.config_manager'
              → 'voicetyper.services.config_manager' olarak loglanır.

    Returns:
        logging.Logger: İlgili modül için yapılandırılmış logger.
    """
    if name == "__main__":
        child_name = "main"
    elif name.startswith("app."):
        child_name = name[len("app."):]   # 'app.' prefix'ini kaldır
    else:
        child_name = name

    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{child_name}")


def _parse_level(level_str: str) -> int:
    """Log seviyesi string'ini logging sabitine dönüştürür."""
    level = getattr(logging, level_str.upper(), None)
    if not isinstance(level, int):
        logging.getLogger(_ROOT_LOGGER_NAME).warning(
            f"Geçersiz log seviyesi '{level_str}', INFO kullanılıyor."
        )
        return logging.INFO
    return level
