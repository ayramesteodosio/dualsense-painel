from . import plataforma

try:
    if not plataforma.LINUX:
        raise ImportError
    from .audio_pulse import HEADPHONES, SPEAKER, MicMeter, find_devices, play_tone
except ImportError:
    from .audio_portable import HEADPHONES, SPEAKER, MicMeter, find_devices, play_tone

__all__ = ["HEADPHONES", "SPEAKER", "MicMeter", "find_devices", "play_tone"]
