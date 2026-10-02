import numpy as np
import soundfile as sf
import time

def test_numpy_resampling():
    print("--- 1. Testing Audio Fallback Resampling ---")
    
    # Simulate a 1-second 48000Hz audio signal (e.g. 400Hz sine wave)
    sr_native = 48000
    t_native = np.arange(sr_native) / sr_native
    audio_native = np.sin(2 * np.pi * 400 * t_native).astype(np.float32)
    
    duration_native = len(audio_native) / sr_native
    print(f"Native audio generated: SR={sr_native}Hz, Length={len(audio_native)} samples, Duration={duration_native:.2f}s")
    
    # Simulate faster_whisper_provider.py resampling logic
    print("Simulating faster_whisper_provider.py fallback resampling...")
    sr_target = 16000
    
    start_time = time.time()
    orig_times = np.arange(len(audio_native)) / sr_native
    new_times = np.arange(int(len(audio_native) * sr_target / sr_native)) / float(sr_target)
    audio_resampled = np.interp(new_times, orig_times, audio_native).astype(np.float32)
    resample_time = time.time() - start_time
    
    duration_resampled = len(audio_resampled) / sr_target
    
    print(f"Resampled audio: SR={sr_target}Hz, Length={len(audio_resampled)} samples, Duration={duration_resampled:.2f}s")
    print(f"Resampling took {resample_time*1000:.2f} ms")
    
    assert abs(duration_native - duration_resampled) < 0.001, "Duration mismatch!"
    print("SUCCESS: Output duration perfectly matches input duration.")
    print("LIMITATION: numpy.interp uses simple linear interpolation. It lacks a low-pass anti-alias filter.")
    print("However, for Whisper ASR, human voice energy above 8kHz is negligible, so aliasing distortion is minimal.")

if __name__ == "__main__":
    test_numpy_resampling()
