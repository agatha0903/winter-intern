import time
import threading
import math
import numpy as np
import sounddevice as sd
import os
import sys

from rtde_control import RTDEControlInterface
from rtde_receive import RTDEReceiveInterface

from kokoro_onnx import Kokoro


ROBOT_IP = "192.168.0.61"  # 본인의 URSim/로봇 IP로 변경 필수
ROBOT_SPEED = 0.01
ROBOT_ACCEL = 0.1


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KOKORO_MODEL_PATH = os.path.join(BASE_DIR, "data", "kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.path.join(BASE_DIR, "data", "voices-v1.0.bin")


class BriefingSystem:
    def __init__(self):
        print("[TTS] Loading Kokoro...")
        try:
            self.tts = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
            self.is_speaking = False
        except Exception as e:
            print(f"[TTS Error] {e}")
            print("모델 파일 경로를 확인해주세요.")
            self.tts = None

    def _speak_thread(self, text):
        """실제 오디오 생성 및 재생을 담당하는 내부 함수"""
        if not self.tts: return

        self.is_speaking = True
        try:
            samples, sr = self.tts.create(text, voice="af_sarah", speed=1, lang="en-us")
            sd.play(samples, samplerate=sr)
            sd.wait()
        except Exception as e:
            print(f"[TTS Error] {e}")
        finally:
            self.is_speaking = False

    def announce(self, text):
        if self.is_speaking:
            return

        print(f"[Briefing] {text}")
        self.t = threading.Thread(target=self._speak_thread, args=(text,))
        self.t.start()

def main():
    briefing = BriefingSystem()

    print(f"[ROBOT] Connecting to {ROBOT_IP}...")
    try:
        rtde_c = RTDEControlInterface(ROBOT_IP)
        rtde_r = RTDEReceiveInterface(ROBOT_IP)
        print("[ROBOT] Connection Successful!")
    except Exception as e:
        print(f"[ROBOT ERROR] 연결 실패: {e}")
        print("URSim이 켜져 있는지, IP가 정확한지 확인하세요.")
        sys.exit(1)

    try:
        start_pose = rtde_r.getActualTCPPose()
        target_pose = list(start_pose)
        target_pose[1] -= 0.05
        target_pose[0] -= 0.05
        target_pose[2] -= 0

        print(f'Start point: {start_pose} -> Target point: {target_pose}')

        # 이동 전 안내
        briefing.announce(f"Initiating descent sequence. Target speed is {ROBOT_SPEED} meters per second.")
        time.sleep(3.0)


        rtde_c.moveL(target_pose, ROBOT_SPEED, ROBOT_ACCEL, True)

        said_start = False
        said_mid = False

        start_z = start_pose[1]
        target_z = target_pose[1]
        total_dist_to_move = abs(start_z - target_z)

        time.sleep(0.1)

        while True:
            curr_pose = rtde_r.getActualTCPPose()
            curr_z = curr_pose[1]
            dist_moved = abs(start_z - curr_z)

            if total_dist_to_move > 0:
                progress = (dist_moved / total_dist_to_move) * 100
            else:
                progress = 100

            # C. 브리핑 로직
            # if progress > 10 and not said_start:
            #     msg = f"Movement started. Speed is {ROBOT_SPEED} meters per second."
            #     briefing.announce(msg)
            #     said_start = True

            # 목표 지점과의 남은 거리 계산
            remaining = abs(curr_z - target_z)

            if remaining < 0.001:
                break

            time.sleep(0.05)  # 20Hz 주기로 체크 (CPU 점유율 조절)

        rtde_c.stopL()

        end_pose = rtde_r.getActualTCPPose()

        actual_distance = math.sqrt((end_pose[0] - start_pose[0]) ** 2 + (end_pose[1] - start_pose[1]) ** 2 + (end_pose[2] - start_pose[2]) ** 2)
        #위의 dist_moved 변수랑 같은 값이 나오지만, 추후 z축 이외의 다른 경로를 움직일 것을 대비해 추가 생성.
        msg= f"Target position reached. Robot moved total {actual_distance:.2f} meters."
        briefing.announce(msg)

        if briefing.t is not None and briefing.t.is_alive():
            briefing.t.join()

    except KeyboardInterrupt:
        print("\n[ROBOT] Interrupted by User!")
        rtde_c.stopL()
        rtde_c.stopScript()

    except Exception as e:
        print(f"[ROBOT ERROR] {e}")
        rtde_c.stopL()

    finally:
        rtde_c.stopScript()
        rtde_c.disconnect()
        rtde_r.disconnect()
        #print("[ROBOT] Disconnected.")


if __name__ == "__main__":
    main()