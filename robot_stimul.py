#!/usr/bin/env python
import argparse
import logging
import sys
import datetime
import time
import random  # 센서 노이즈 시뮬레이션을 위해 추가

# ==========================================
# [Simulation] 가짜 로봇 라이브러리 (Mock Classes)
# 실제 라이브러리가 없어도 돌아가도록 흉내 냅니다.
# ==========================================

# 전역 변수로 현재 로봇의 가상 위치 저장
# 초기 위치 (x, y, z, rx, ry, rz)
current_sim_pose = [-0.0953, -0.4155, 0.37, 0.0, 3.14, 0.0]


class MockRTDEControl:
    def __init__(self, ip):
        print(f"[SIM] Connecting to Robot Control at {ip}...")
        time.sleep(0.5)
        print("[SIM] Control Connected.")

    def moveL(self, pose, speed, acceleration):
        global current_sim_pose
        print(f"\n[SIM] Robot Moving... Speed: {speed:.3f} m/s")
        # 실제 로봇이 움직이는 시간 흉내 (거리에 따라 다르겠지만 단순화)
        time.sleep(0.2)
        current_sim_pose = pose  # 이동 완료 처리
        print(f"[SIM] Reached Position: x={pose[0]:.4f}, y={pose[1]:.4f}, z={pose[2]:.4f}")

    def stopScript(self):
        print("[SIM] Script Stopped.")


class MockRTDEReceive:
    def __init__(self, ip):
        print(f"[SIM] Connecting to Robot Receive at {ip}...")

    def getActualTCPPose(self):
        global current_sim_pose
        return current_sim_pose


class MockRTDEState:
    def __init__(self):
        global current_sim_pose
        # 실제 센서처럼 아주 미세한 떨림(Noise) 추가
        noise = lambda: random.uniform(-0.00005, 0.00005)
        noisy_pose = [val + noise() for val in current_sim_pose]

        self.actual_TCP_pose = noisy_pose
        self.target_TCP_pose = current_sim_pose


class MockRTDEConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def connect(self):
        print(f"[SIM] RTDE Connection Established on {self.port}")

    def get_controller_version(self):
        pass

    def send_output_setup(self, names, types, frequency):
        print(f"[SIM] Output Configured at {frequency}Hz")
        return True

    def send_start(self):
        print("[SIM] Data Synchronization Started")
        return True

    def receive(self, binary):
        # 현재 상태를 담은 객체 반환
        return MockRTDEState()

    def receive_buffered(self, binary):
        return MockRTDEState()

    def send_pause(self):
        print("[SIM] RTDE Paused")

    def disconnect(self):
        print("[SIM] RTDE Disconnected")


class MockConfig:
    def __init__(self, filename):
        pass

    def get_recipe(self, name):
        # 가짜 레시피 리턴
        return (["timestamp", "actual_TCP_pose", "target_TCP_pose"], ["DOUBLE", "VECTOR6D", "VECTOR6D"])


# ==========================================
# [Main Code] 기존 코드 로직 (라이브러리만 교체됨)
# ==========================================

# parameters
parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1", help="Simulated IP")
parser.add_argument("--port", type=int, default=30004)
parser.add_argument("--samples", type=int, default=0)
parser.add_argument("--frequency", type=int, default=100)
parser.add_argument("--config", default="record_configuration.xml")  # 실제 파일 없어도 됨
parser.add_argument("--output", default="robot_data.csv")
parser.add_argument("--verbose", action="store_true")
parser.add_argument("--buffered", action="store_true")
parser.add_argument("--binary", action="store_true")
args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.INFO)

# --- [변경] Mock 클래스로 초기화 ---
rtde_c = MockRTDEControl(args.host)
rtde_r = MockRTDEReceive(args.host)
# -------------------------------

current_tcp_pose = rtde_r.getActualTCPPose()

num_positions = 100  # 테스트용으로 10개만 하려면 여기 수정
points = []
x, y, z, rx, ry, rz = current_tcp_pose

# Generate Path (기존 로직 동일)
for i in range(1, num_positions + 1):
    y = y - 0.0001
    pointt = [x, y, z, rx, ry, rz]
    points.append(pointt)

velocities_mm = []
accelerations_mm2 = []
pause_times = []

for i in range(1, num_positions + 1):
    velocities_mm.append(10)
    accelerations_mm2.append(10)
    pause_times.append(0.2)  # 시뮬레이션 속도를 위해 0.2초 유지

velocities_m = [v * 0.001 for v in velocities_mm]
accelerations_m = [a * 0.001 for a in accelerations_mm2]

# --- [변경] Mock 클래스로 설정 ---
conf = MockConfig(args.config)
output_names, output_types = conf.get_recipe("out")

con = MockRTDEConnection(args.host, args.port)
con.connect()
con.get_controller_version()
con.send_output_setup(output_names, output_types, frequency=args.frequency)
con.send_start()
# -------------------------------

csv_file = 'robot_data_SIMULATION_{}.csv'.format(datetime.datetime.now().strftime('%Y-%m-%d %H_%M_%S.%f')[:-3])
print(f"Logging data to: {csv_file}")

with open(csv_file, 'w') as csvfile:
    # 헤더 작성 (간단하게 구현)
    csvfile.write(
        "timestamp actual_TCP_pose_0 actual_TCP_pose_1 actual_TCP_pose_2 actual_TCP_pose_3 actual_TCP_pose_4 actual_TCP_pose_5 target_TCP_pose_0 target_TCP_pose_1 target_TCP_pose_2 target_TCP_pose_3 target_TCP_pose_4 target_TCP_pose_5\n")

    i = 1
    keep_running = True

    for j, point in enumerate(points):
        print(f"Moving to point {j + 1}/{num_positions}...")

        # [SIM] 로봇 이동 명령 (가짜함수)
        rtde_c.moveL(point, velocities_m[j], accelerations_m[j])

        print(f"Arrived at point {j + 1}. Pausing {pause_times[j]} sec...")

        pause_start = time.time()
        while time.time() - pause_start < pause_times[j]:
            if args.samples > 0 and i >= args.samples:
                keep_running = False

            try:
                # [SIM] 데이터 수신 (가짜함수)
                if args.buffered:
                    state = con.receive_buffered(args.binary)
                else:
                    state = con.receive(args.binary)

                if state is not None:
                    tims = [datetime.datetime.now().strftime('%Y-%m-%d %H_%M_%S.%f')[:-3]]
                    # [SIM] MockState 객체에서 데이터 꺼내기
                    data_info = tims + state.actual_TCP_pose + state.target_TCP_pose
                    row = ' '.join(map(str, data_info)) + '\n'
                    csvfile.write(row)
                    i += 1

                    # 시뮬레이션이 너무 빨리 끝나지 않도록 약간의 딜레이 (100Hz 흉내)
                    time.sleep(1.0 / args.frequency)

            except KeyboardInterrupt:
                keep_running = False

        if not keep_running:
            break

        if j == len(points) - 1:
            print(f"Reached final point {j + 1}. Stopping execution.")
            break

sys.stdout.write("\rComplete!            \n")

con.send_pause()
con.disconnect()
rtde_c.stopScript()