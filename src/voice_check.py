import torchaudio
import sys
import numpy as np
sys.modules['torchcodec'] = None
if not hasattr(torchaudio, 'list_audio_backends'):
    torchaudio.list_audio_backends = lambda: ["soundfile"]
import os
import sounddevice as sd
from scipy.io.wavfile import write
from speechbrain.inference.speaker import SpeakerRecognition


class SpeakerAuth:
    def __init__(self, master_file="master_voice.wav", temp_file="temp_input.wav"):
        self.master_file = master_file
        self.temp_file = temp_file

        print("[Auth] 모델을 불러오는 중입니다... (ECAPA-TDNN)")
        self.verification = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb"
        )
        print("[Auth] 모델 로드 완료.")

    def record_audio(self, filename, duration=4, fs=16000):
        """마이크로 지정된 시간만큼 녹음하여 파일로 저장"""
        print(f" {duration}초간 말씀해주세요...")
        try:
            recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
            sd.wait()  # 녹음 끝날 때까지 대기
            write(filename, fs, recording)  # wav 파일로 저장
            print("녹음 완료.")
        except Exception as e:
            print(f"[Auth Error] 녹음 중 오류 발생: {e}")

    def verify(self):
        """현재 마이크 입력과 마스터 파일 비교"""
        # 1. 마스터 파일이 없으면 현재 목소리를 마스터로 등록
        if not os.path.exists(self.master_file):
            print("등록된 사용자 목소리가 없습니다.")
            print("최초 사용자를 마스터로 등록합니다.")
            self.record_audio(self.master_file)
            return True, 1.0  # 자동 승인

        # 2. 인증을 위한 녹음 (임시 파일)
        self.record_audio(self.temp_file)

        try:
            score, prediction = self.verification.verify_files(
                self.master_file,
                self.temp_file
            )

            similarity = score.item()
            is_same_person = bool(prediction.item())

            return is_same_person, similarity

        except Exception as e:
            print(f"[Auth Error] 검증 중 오류 발생: {e}")
            return False, 0.0