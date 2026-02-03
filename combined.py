import os
import csv
import json
import re
import time
import queue
import threading
import sys
from datetime import datetime
from time import perf_counter

import numpy as np
import sounddevice as sd
import whisper

# === [Imports] ===
# src 폴더가 없거나 경로가 다르면 수정 필요
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
try:
    import rtde_control
    import rtde_receive
    from src.minilm import MiniLMRetriever
    from src.router import IntentRouter
    from src.briefing import BriefingSystem
except ImportError as e:
    print(f"오류: 필수 모듈을 불러올 수 없습니다. {e}")
    sys.exit(1)

# ======================
# 설정 (Settings)
# ======================
SAMPLE_RATE = 16000
INPUT_DEVICE = 1  # 마이크 장치 번호 (안 되면 None)
WHISPER_MODEL = ("small")

# [VAD 설정: 말 끊김 감지]
CHUNK_MS = 30
ENERGY_THRESHOLD = 0.012
MIN_SPEECH_SEC = 0.25
END_SILENCE_SEC = 0.55  # 이 시간만큼 조용하면 말이 끝난 것으로 간주
MAX_UTT_SEC = 4.5

# [로봇 설정]
HOST = "192.168.0.61"
BASE_SPEED = 0.25
BASE_ACC = 0.5
XYZ_LIMITS = {"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (0.0, 1.2)}

# [데이터 파일]
INTENT_BANK_PATH = "data/intent_bank_JH.json"
THRESHOLD = 0.55

# [키워드]
STOP_KEYWORDS = ["stop", "pause", "hold on", "wait", "halt", "freeze", "emergency"]
START_KEYWORDS = ["start", "begin", "continue", "go", "resume", "arm"]
PAIN_KEYWORDS = ["it hurts", "hurt", "pain", "ouch"]

DIR_WORDS = {
    "up": ("z", +1), "down": ("z", -1),
    "left": ("y", +1), "right": ("y", -1),
    "forward": ("x", +1), "back": ("x", -1), "backward": ("x", -1),
}


# ======================
# 1. 로깅 클래스 (CSV 생성)
# ======================
class MetricsCSV:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.f = open(path, "w", newline="", encoding="utf-8-sig")

        # ▼ 사용자가 원하는 데이터 컬럼 정의
        self.fields = [
            "timestamp",  # 로그 찍힌 시각
            "event_type",  # 이벤트 타입 (Safety, AI_Intent, Rule_Move...)
            "text",  # 인식된 텍스트
            "asr_time",  # 위스퍼가 글자로 바꾸는 데 걸린 시간
            "total_latency",  # ★ [핵심] 말 끝남 ~ 로봇 동작 시작까지 걸린 시간
            "description"  # 상세 설명
        ]
        self.w = csv.DictWriter(self.f, fieldnames=self.fields)
        self.w.writeheader()
        self.f.flush()

    def log(self, event_type, text, asr_time, total_latency, description):
        row = {
            "timestamp": datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "event_type": event_type,
            "text": text,
            "asr_time": asr_time,
            "total_latency": total_latency,
            "description": description
        }
        self.w.writerow(row)
        self.f.flush()

    def close(self):
        try:
            self.f.close()
        except:
            pass


# ======================
# 2. 실시간 리스너 (시간 측정 기능 추가)
# ======================
class RealtimeWhisper:
    def __init__(self, asr_model, sample_rate=16000, input_device=None):
        self.asr = asr_model
        self.sr = sample_rate
        self.device = input_device
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self._stream = None

        # 프레임 계산
        self.chunk_frames = int(self.sr * (CHUNK_MS / 1000.0))
        self.min_speech_frames = int(self.sr * MIN_SPEECH_SEC)
        self.end_silence_frames = int(self.sr * END_SILENCE_SEC)
        self.max_utt_frames = int(self.sr * MAX_UTT_SEC)

    def _audio_cb(self, indata, frames, time_info, status):
        if status: print("[AUDIO ERROR]", status)
        self.q.put(indata[:, 0].copy())

    def start(self):
        self.stop_event.clear()
        self._stream = sd.InputStream(
            samplerate=self.sr, channels=1, dtype="float32",
            blocksize=self.chunk_frames, device=self.device,
            callback=self._audio_cb
        )
        self._stream.start()

    def stop(self):
        self.stop_event.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def listen_texts(self):
        """음성을 감지하여 텍스트와 '말이 끝난 시간'을 반환"""
        in_speech = False
        utt = np.zeros((0,), dtype=np.float32)
        silence = 0

        while not self.stop_event.is_set():
            try:
                chunk = self.q.get(timeout=0.2)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
            is_speech = rms > ENERGY_THRESHOLD

            if is_speech:
                in_speech = True
                silence = 0
                utt = np.concatenate([utt, chunk])

                # 너무 길면 강제 종료
                if len(utt) > self.max_utt_frames:
                    voice_end_time = time.time()  # 강제 종료 시점
                    result = self._transcribe_utt(utt, voice_end_time)
                    if result: yield result
                    utt = np.zeros((0,), dtype=np.float32)
                    in_speech = False
            else:
                if in_speech:
                    silence += len(chunk)
                    utt = np.concatenate([utt, chunk])

                    # 조용함이 지속되면 말 끝남 판단
                    if silence >= self.end_silence_frames:
                        if len(utt) >= self.min_speech_frames:
                            # ★ [핵심] 말이 정확히 끝난 시점 기록
                            # 현재 시간에서 침묵 시간(END_SILENCE_SEC)을 뺌
                            voice_end_time = time.time() - END_SILENCE_SEC

                            result = self._transcribe_utt(utt, voice_end_time)
                            if result: yield result

                        utt = np.zeros((0,), dtype=np.float32)
                        in_speech = False
                        silence = 0

    def _transcribe_utt(self, audio_1d: np.ndarray, voice_end_time: float):
        """Whisper 변환 및 시간 정보 패키징"""
        t0 = perf_counter()

        # Whisper 추론
        res = self.asr.transcribe(
            audio_1d, language="en", fp16=False,
            beam_size=1, best_of=1, temperature=0.0
        )

        t1 = perf_counter()
        asr_duration = t1 - t0  # 순수 추론 시간
        text = (res.get("text") or "").strip()

        if not text: return None

        return {
            "text": text,
            "asr_time": asr_duration,
            "voice_end_time": voice_end_time  # 말이 끝난 절대 시각
        }


# ======================
# 3. 로봇 제어 및 헬퍼 함수
# ======================
def load_intent_bank(path: str):
    with open(path, "r", encoding="utf-8") as f: return json.load(f)


def override_safety(text: str):
    t = text.lower()
    if any(k in t for k in PAIN_KEYWORDS): return "PAIN"
    if any(k in t for k in STOP_KEYWORDS): return "STOP"
    if any(k in t for k in START_KEYWORDS): return "START"
    return None


def parse_move_command(text: str):
    t = text.lower()
    found_dir = None
    for w in DIR_WORDS.keys():
        if re.search(rf"\b{w}\b", t):
            found_dir = w
            break
    if not found_dir: return None

    dist = 0.05
    m = re.search(r"(\d+(\.\d+)?)\s*(cm|centimeter)", t)
    if m: dist = float(m.group(1)) / 100.0

    axis, sign = DIR_WORDS[found_dir]
    dx, dy, dz = 0.0, 0.0, 0.0
    if axis == "x":
        dx = sign * dist
    elif axis == "y":
        dy = sign * dist
    else:
        dz = sign * dist

    return dx, dy, dz, found_dir


def safe_stop(rtde_c):
    try:
        rtde_c.stopL(2.0)
    except:
        rtde_c.stopJ(2.0)


def moveL_delta(rtde_c, rtde_r, dx, dy, dz, speed, acc):
    pose = rtde_r.getActualTCPPose()
    target = list(pose)
    target[0] += dx;
    target[1] += dy;
    target[2] += dz
    # 리미트 적용
    target[0] = max(XYZ_LIMITS["x"][0], min(XYZ_LIMITS["x"][1], target[0]))
    target[1] = max(XYZ_LIMITS["y"][0], min(XYZ_LIMITS["y"][1], target[1]))
    target[2] = max(XYZ_LIMITS["z"][0], min(XYZ_LIMITS["z"][1], target[2]))
    rtde_c.moveL(target, speed, acc, True)


def handle_intent_briefing(intent, rtde_c, rtde_r, state, briefing):
    """동작 수행 및 브리핑"""
    intent = intent.upper()

    if intent == "STOP":
        safe_stop(rtde_c)
        state["armed"] = False
        briefing.announce("Stopping.")
        return "Emergency Stop"

    if intent == "PAIN":
        safe_stop(rtde_c)
        time.sleep(0.1)
        moveL_delta(rtde_c, rtde_r, 0, 0, 0.05, BASE_SPEED, BASE_ACC)
        state["armed"] = False
        briefing.announce("Backing off.")
        return "Pain Reaction"

    if intent == "START":
        state["armed"] = True
        briefing.announce("System armed.")
        return "System Armed"

    if intent == "MOVE_SLOW":
        state["speed_scale"] = 0.5
        briefing.announce("Speed decreased.")
        return "Speed 50%"

    if intent == "OK":
        state["speed_scale"] = 1.0
        briefing.announce("Normal speed.")
        return "Speed 100%"

    return "Unhandled Intent"


# ======================
# 4. 메인 실행 (MAIN)
# ======================
def main():
    listener = None
    rtde_c = None

    # 로그 파일 생성
    log_name = f"logs/latency_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    metrics = MetricsCSV(log_name)
    briefing = BriefingSystem()

    try:
        print(">>> [INIT] Loading Whisper...")
        asr = whisper.load_model(WHISPER_MODEL)

        print(">>> [INIT] Loading MiniLM & Router...")
        bank = load_intent_bank(INTENT_BANK_PATH)
        retriever = MiniLMRetriever(bank)
        router = IntentRouter(retriever, threshold=THRESHOLD)

        print(f">>> [INIT] Connecting to Robot ({HOST})...")
        rtde_c = rtde_control.RTDEControlInterface(HOST)
        rtde_r = rtde_receive.RTDEReceiveInterface(HOST)

        state = {"armed": False, "speed_scale": 1.0}
        briefing.announce("Ready to start.")
        print("\n=== System Ready (Say 'Start' to begin) ===\n")

        # 리스너 시작
        listener = RealtimeWhisper(asr)
        listener.start()

        for res in listener.listen_texts():
            text = res["text"]
            asr_time = res["asr_time"]  # 위스퍼 처리 시간 (초)
            voice_end_time = res["voice_end_time"]  # 말이 끝난 시각 (절대시간)

            print(f"\n🗣️ User: '{text}'")

            # ---------------------------------------------------------
            # [A] Safety Override (최우선)
            # ---------------------------------------------------------
            ov_intent = override_safety(text)
            if ov_intent:
                desc = handle_intent_briefing(ov_intent, rtde_c, rtde_r, state, briefing)

                # ★ 지연시간 계산: (현재시각 - 말 끝난 시각)
                total_latency = time.time() - voice_end_time

                metrics.log("Safety_Override", text, f"{asr_time:.3f}", f"{total_latency:.3f}", desc)
                print(f"Latency: {total_latency:.3f}s (Action: {desc})")
                continue

            # ---------------------------------------------------------
            # [B] Armed Check
            # ---------------------------------------------------------
            if not state["armed"]:
                print("Ignored (Not Armed)")
                metrics.log("Ignored", text, f"{asr_time:.3f}", "-", "Not armed")
                continue

            # ---------------------------------------------------------
            # [C] Rule Move (텍스트 기반 이동)
            # ---------------------------------------------------------
            move_data = parse_move_command(text)
            if move_data:
                dx, dy, dz, dname = move_data
                spd = BASE_SPEED * state["speed_scale"]

                # 로봇 명령 시작
                moveL_delta(rtde_c, rtde_r, dx, dy, dz, spd, BASE_ACC)
                briefing.announce(f"Moving {dname}.")

                # ★ 지연시간 계산
                total_latency = time.time() - voice_end_time

                metrics.log("Rule_Move", text, f"{asr_time:.3f}", f"{total_latency:.3f}", f"Move {dname}")
                print(f"Latency: {total_latency:.3f}s (Move {dname})")
                continue

            # ---------------------------------------------------------
            # [D] AI Intent (MiniLM)
            # ---------------------------------------------------------
            chosen, _ = router.route(text)
            if chosen:
                intent = chosen["intent"]
                desc = handle_intent_briefing(intent, rtde_c, rtde_r, state, briefing)

                # ★ 지연시간 계산
                total_latency = time.time() - voice_end_time

                metrics.log("AI_Intent", text, f"{asr_time:.3f}", f"{total_latency:.3f}",
                            f"{intent} ({chosen['score']:.2f})")
                print(f"⏱️ Latency: {total_latency:.3f}s (Intent: {intent})")
            else:
                briefing.announce("Unknown command.")
                metrics.log("Unknown", text, f"{asr_time:.3f}", "-", "Low confidence")
                print("Unknown command")

    except KeyboardInterrupt:
        print("\n🛑 Stopped by User")
        briefing.announce("Shutting down.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        if listener: listener.stop()
        if rtde_c:
            try:
                rtde_c.stopL(); rtde_c.stopScript()
            except:
                pass
        if metrics: metrics.close()


if __name__ == "__main__":
    main()