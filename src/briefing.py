import os
import threading
import sounddevice as sd
from kokoro_onnx import Kokoro


class BriefingSystem:
    def __init__(self):
        self.tts = None
        self.is_speaking = False
        self.thread = None

        # 2. 경로 설정 (src 폴더 기준 한 단계 위로 올라가기)
        try:
            # 현재 파일 위치: .../jeehe_project/src
            current_dir = os.path.dirname(os.path.abspath(__file__))

            # 프로젝트 루트: .../jeehe_project (한 단계 위)
            project_root = os.path.dirname(current_dir)

            # 데이터 폴더 경로 조합
            model_path = os.path.join(project_root, "data", "kokoro-v1.0.onnx")
            voices_path = os.path.join(project_root, "data", "voices-v1.0.bin")

            print(f"[TTS] Loading Kokoro from: {os.path.join(project_root, 'data')}")

            # 3. 모델 로드 시도
            self.tts = Kokoro(model_path, voices_path)
            print("[TTS] Engine Ready.")

        except Exception as e:
            # 에러가 나도 변수는 이미 초기화되어 있으므로 프로그램은 죽지 않음
            print(f"[TTS Error] 모델 로드 실패: {e}")
            print("경로가 올바른지, data 폴더가 src 폴더 '밖에' 있는지 확인하세요.")
            self.tts = None

    def _speak_thread(self, text):
        """내부적으로 실행되는 말하기 스레드"""
        if not self.tts: return

        self.is_speaking = True
        try:
            # 음성 생성 (속도, 목소리 변경 가능)
            samples, sr = self.tts.create(text, voice="af_sarah", speed=1.0, lang="en-us")
            sd.play(samples, samplerate=sr)
            sd.wait()  # 다 말할 때까지 대기
        except Exception as e:
            print(f"[TTS Play Error] {e}")
        finally:
            self.is_speaking = False

    def announce(self, text):
        """외부에서 호출하는 함수 (비동기 말하기)"""
        # 이미 말하고 있으면 스킵 (중복 방지)
        if self.tts is None:
            print(f"[Briefing (No Audio)] {text}")
            return
        if self.is_speaking:
            return

        print(f"[Briefing] {text}")

        # 새로운 스레드 시작
        self.thread = threading.Thread(target=self._speak_thread, args=(text,))
        self.thread.start()

    def wait_until_finished(self):
        """현재 하고 있는 말이 끝날 때까지 대기 (프로그램 종료 전 사용)"""
        if self.thread is not None and self.thread.is_alive():
            print("[TTS] Waiting for speech to finish...")
            self.thread.join()