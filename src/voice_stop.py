import threading
import speech_recognition as sr
import whisper
import os
import time

# 감지할 키워드 목록 (한국어, 영어 혼용)
STOP_KEYWORDS = ["stop", "bad", "turn off", "멈춰", "정지", "위험", "스탑"]


class VoiceEmergencySystem:
    def __init__(self, rtde_c, log_callback=None):
        """
        :param rtde_c: 로봇 제어 객체 (비상시 직접 정지 명령을 내리기 위해 필요)
        """
        self.rtde_c = rtde_c
        self.log_callback = log_callback
        self.stop_flag = False  # 메인 루프 탈출용 플래그
        self.running = True  # 리스닝 스레드 유지용 플래그

        print("[Voice] Loading Whisper Model (tiny)...")
        try:
            self.model = whisper.load_model("base")
            print("[Voice] Model Loaded.")
        except Exception as e:
            print(f"[Voice Error] 모델 로드 실패: {e}")
            self.model = None

    def _listening_thread(self):
        """백그라운드에서 실행될 리스닝 로직"""
        if not self.model: return

        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True
        temp_filename = "temp_voice_command.wav"

        with sr.Microphone() as source:
            print("[Voice] Listening for 'STOP' commands...")
            r.adjust_for_ambient_noise(source, duration=1)

            while self.running and not self.stop_flag:
                try:
                    # 3초 단위로 끊어서 듣기 (너무 길게 들으면 반응 느려짐)
                    audio = r.listen(source, timeout=None, phrase_time_limit=3)

                    with open(temp_filename, "wb") as f:
                        f.write(audio.get_wav_data())

                    # Whisper로 텍스트 변환
                    result = self.model.transcribe(temp_filename, fp16=False)
                    text = result['text'].lower().strip()

                    if text:
                        print(f"[Voice Heard] '{text}'")

                        # 키워드 매칭 확인
                        if any(k in text for k in STOP_KEYWORDS):
                            if self.log_callback:
                                self.log_callback(f"로봇 비상 정지 동작 감지 및 실행")
                            self.rtde_c.stopL(2.0)
                            self.stop_flag = True
                            break

                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    pass

        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass

    def start(self):
        """감시 시작"""
        if self.model is None:
            print("[Voice] 모델이 없어 음성 감시를 시작하지 못합니다.")
            return

        self.running = True
        self.stop_flag = False
        t = threading.Thread(target=self._listening_thread, daemon=True)
        t.start()

    def is_triggered(self):
        """외부에서 비상 정지가 눌렸는지 확인하는 함수"""
        return self.stop_flag

    def stop(self):
        """감시 종료 (프로그램 끝날 때 호출)"""
        self.running = False
