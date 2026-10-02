"""
test_single_instance.py
"""
import subprocess
import time
import os
import sys

def test_single_instance():
    print("Main process başlatılıyor...")
    main_proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd="C:\\Users\\ozdem\\Desktop\\Yazılım\\Projeler\\Voice Typer",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for it to start
    time.sleep(2)
    
    print("İkinci process başlatılıyor...")
    second_proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd="C:\\Users\\ozdem\\Desktop\\Yazılım\\Projeler\\Voice Typer",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for second process to exit
    second_proc.wait(timeout=3)
    
    out, err = second_proc.communicate()
    out = out.decode("utf-8", errors="ignore")
    err = err.decode("utf-8", errors="ignore")
    
    print(f"İkinci process exit code: {second_proc.returncode}")
    print(f"İkinci process Output: {out}")
    print(f"İkinci process Error: {err}")
    
    assert second_proc.returncode == 0 or second_proc.returncode == 1, "Beklenmedik crash!"
    assert "Voice Typer zaten çalışıyor" in out or "Voice Typer zaten çalışıyor" in err, "Single instance mesaji alinmadi!"
    
    # Kill main proc
    print("Main process hala ayakta mi?")
    assert main_proc.poll() is None, "Main process çökmüş!"
    
    print("Main process sağlıklı. Test Başarılı.")
    main_proc.terminate()
    
if __name__ == "__main__":
    test_single_instance()
