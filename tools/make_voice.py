"""Make the narrator's voice recordings with an offline neural voice (Piper), so the guided demo has a clear, natural voice with no internet.

Run it with the voice tool's own environment (`.venv_voice`), not the project's: build_voice.bat does that for you.
  python tools/make_voice.py samples            -> a short sample of every downloaded voice, to listen to and choose from
  python tools/make_voice.py clips VOICE        -> recordings of every sentence the demo speaks (needs the sentence list from build_voice.bat)

Everything stays on this computer. The voices are files in voice_models/ (downloaded once, kept out of git).
"""
from __future__ import annotations

import base64
import io
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "voice_models"
SAMPLE_TEXT = ("Autonomous experiments, day and night. The arm lifted the drug bottle. The camera scanned its barcode, read the printed name and looked at the liquid: "
               "all three agree, so the answer is right bottle.")
SPEED = 1.08            # a little slower than the voice's default: easier to follow in a demo (a larger number is slower)


def load(name: str):
    from piper import PiperVoice
    path = MODELS / f"{name}.onnx"
    if not path.exists():
        raise SystemExit(f"The voice '{name}' is not downloaded: {path} is missing.")
    return PiperVoice.load(str(path))


def speak(voice, text: str) -> bytes:
    """A WAV file's bytes."""
    from piper import SynthesisConfig
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=SPEED))
    return buffer.getvalue()


def to_mp3(wav_bytes: bytes) -> bytes:
    """MP3 plays in every browser; a spoken-word clip at this size is small."""
    import soundfile
    data, rate = soundfile.read(io.BytesIO(wav_bytes))
    out = io.BytesIO()
    soundfile.write(out, data, rate, format="MP3", subtype="MPEG_LAYER_III", bitrate_mode="VARIABLE", compression_level=0.6)
    return out.getvalue()


def samples() -> None:
    folder = ROOT / "runs" / "voice_samples"
    folder.mkdir(parents=True, exist_ok=True)
    for model in sorted(MODELS.glob("*.onnx")):
        name = model.stem
        wav = speak(load(name), SAMPLE_TEXT)
        (folder / f"{name}.wav").write_bytes(wav)
        print(f"sample written: {folder / (name + '.wav')}")


def clips(name: str) -> None:
    lines_file = ROOT / "voice_models" / "narration_lines.json"
    if not lines_file.exists():
        raise SystemExit("The sentence list is missing: run build_voice.bat, which makes it first.")
    sentences = json.loads(lines_file.read_text(encoding="utf-8"))
    voice = load(name)
    out: dict[str, str] = {}
    total = 0
    for i, item in enumerate(sentences, 1):
        mp3 = to_mp3(speak(voice, item["text"]))
        out[item["hash"]] = base64.b64encode(mp3).decode("ascii")
        total += len(mp3)
        print(f"  {i}/{len(sentences)}  {len(mp3) // 1024} KB  {item['text'][:60]}")
    target = ROOT / "voice_models" / "narration_audio.json"
    target.write_text(json.dumps({"voice": name, "clips": out}, separators=(",", ":")), encoding="utf-8")
    print(f"written {target}  ({total // 1024} KB of audio, voice {name})")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "samples":
        samples()
    elif command == "clips" and len(sys.argv) > 2:
        clips(sys.argv[2])
    else:
        raise SystemExit(__doc__)
