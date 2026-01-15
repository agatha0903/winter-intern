import json
import numpy as np
import sounddevice as sd
import whisper
import soundfile as sf
from kokoro_onnx import Kokoro
import os

from src.minilm import MiniLMRetriever
from src.router import IntentRouter

# ===== 마이크/ASR 설정 =====
SAMPLE_RATE = 16000
RECORD_SECONDS = 3.5 #한번에 듣는 시간
INPUT_DEVICE = 1           # 너의 마이크. (WASAPI로 성공했으면 9로 바꾸기)
WHISPER_MODEL = "base"  # 느리면 "tiny.en"

# ===== 의미 추론 설정 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INTENT_BANK_PATH = os.path.join(BASE_DIR, "data", "intent_bank_en.json")
THRESHOLD = 0.55

KOKORO_MODEL_PATH = os.path.join(BASE_DIR, "data", "kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.path.join(BASE_DIR, "data", "voices-v1.0.bin")
TTS_SAMPLE_RATE = 16000

# 안전: STOP/START는 키워드 우선 처리(권장)
#STOP_KEYWORDS = ["stop", "pause", "hold on", "wait"]
#START_KEYWORDS = ["start", "begin", "continue"]

RESPONSE_MESSAGES = {
    "STOP": "Stopping immediately.",
    "START": "Starting the process.",
    "MOVE_SLOW": "Okay, I will move slowly.",
    "EXPLAIN": "I am currently listening to your commands.",
    "PAIN": "I will call for help immediately.",
    "OK": "It sounds good."
} #의도에 따라 로봇이 뭐라고 말할 지 정리해둔 딕셔너리


def load_intent_bank(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
#json 파일을 딕셔너리로 변환하는 함수

def record_audio(seconds: float) -> np.ndarray:
    print(f"[REC] Speak now ({seconds:.1f}s)...")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=INPUT_DEVICE,
    )
    sd.wait()
    return audio.squeeze() #차원 축소


#def override_intent(text: str):
    t = text.lower()
    if any(k in t for k in STOP_KEYWORDS):
        return {"intent": "STOP", "score": 1.0, "text": text}
    if any(k in t for k in START_KEYWORDS):
        return {"intent": "START", "score": 1.0, "text": text}
    return None


def speak_text(tts_engine: Kokoro, text: str, voice="af_sarah"):
    """
    Kokoro로 텍스트를 오디오로 변환 후 sounddevice로 재생
    """
    if tts_engine is None:
        print(f"[TTS (No Audio)] {text}")
        return
    print(f"[TTS] Speaking: '{text}'...")
    try:
        samples, sr = tts_engine.create(text, voice=voice, speed=1.0, lang="en-us")

    # 2. 재생 (sd.play는 비동기이므로 sd.wait()로 기다려줌)
        sd.play(samples, samplerate=sr)
        sd.wait()
    except Exception as e:
        print(e)


def main():
    print("[ASR] Loading Whisper:", WHISPER_MODEL)
    asr = whisper.load_model(WHISPER_MODEL)

    print("[NLU] Loading MiniLM retriever + router...")
    intent_bank = load_intent_bank(INTENT_BANK_PATH) #대본 읽기
    retriever = MiniLMRetriever(intent_bank)   # sentence-transformers 기반
    router = IntentRouter(retriever, threshold=THRESHOLD)

    print("[TTS] Loading Kokoro ONNX...")
    # 실제 파일 경로에 맞게 수정 필요. 없으면 에러남.
    # kokoro-onnx는 모델 파일(.onnx)과 음성 파일(.json)이 필요함.
    try:
        tts = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
    except Exception as e:
        print(f"[ERROR] Kokoro 로드 실패: {e}")
        print("https://github.com/thewh1teagle/kokoro-onnx 에서 모델 다운로드 필요")
        return

    print("\nr=record, q=quit\n")

    while True:
        cmd = input("Command > ").strip().lower()
        if cmd == "q":
            break

        # 1) 마이크 녹음
        audio = record_audio(RECORD_SECONDS)

        # 2) ASR (음성 -> 텍스트)
        print("[ASR] Transcribing...")
        result = asr.transcribe(audio, language="en", fp16=False)
        text = (result.get("text") or "").strip()
        print("[TEXT]", text if text else "(empty)")

        if not text:
            print()
            continue

        # 3) 안전 키워드 우선
        #forced = override_intent(text)
        #if forced:
            print("\n[OVERRIDE]")
            print(forced)
            print()
            continue

        # 4) MiniLM 의미 추론(의도 라우팅)
        chosen, candidates = router.route(text)

        print("\n[Top-3 candidates]")
        for c in candidates:
            print(f"- {c['intent']:10s} score={c['score']:.3f} ({c['text']})")

        print("\n[CHOSEN]")
        intent_result=chosen
        print(intent_result)

        if intent_result and intent_result["intent"] != "None":
            # Intent 이름을 말하게 할지, 미리 정의된 문장을 말하게 할지 결정
            intent_name = intent_result["intent"]
            response_text = RESPONSE_MESSAGES.get(intent_name, f"I understand {intent_name}, but I don't know what to say.")
            #RESPONSE_MASSAGES에서 의도에 맞는 대사 찾아옴
            speak_text(tts, response_text,voice="af_sarah")

        elif intent_result and intent_result["intent"] == "None":
            speak_text(tts, "I'm sorry, I didn't understand that.", voice="af_sarah")

        #if forced:
        #    intent_name = forced['intent']
        #   print(f"[OVERRIDE] {intent_name}")

        #    response_text = RESPONSE_MESSAGES.get(intent_name, f"Executing {intent_name}.")
        #    speak_text(tts, response_text)
        #    continue
        print()


if __name__ == "__main__":
    main()
