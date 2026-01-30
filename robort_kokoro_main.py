import time
import csv
import math
import sys
import os
import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from src.briefing import BriefingSystem
from src.voice_stop import VoiceEmergencySystem

from rtde_control import RTDEControlInterface
from rtde_receive import RTDEReceiveInterface

ROBOT_IP = "192.168.0.61"
ROBOT_SPEED = 0.025
ROBOT_ACCEL = 0.1
BRIEFING_INTERVAL = 5.0
LOG_FILENAME = f"event_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

def get_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)

def init_log_file():
    with open('log.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'event tag'])
    print(f"log file {LOG_FILENAME}이 생성되었습니다.")

def log_time(tag):
    now_str = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{now_str}] {tag}")
    with open(LOG_FILENAME, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([now_str, tag])

def main():
    init_log_file()
    briefing = BriefingSystem()

    print(f"[ROBOT] Connecting to {ROBOT_IP}...")
    try:
        rtde_c = RTDEControlInterface(ROBOT_IP)
        rtde_r = RTDEReceiveInterface(ROBOT_IP)
        print("[ROBOT] Connection Successful!")
    except Exception as e:
        print(f"[ROBOT ERROR] 연결 실패: {e}")
        sys.exit(1)

    voice_system = VoiceEmergencySystem(rtde_c, log_callback=log_time)
    voice_system.start()

    time.sleep(1.0)

    try:
        # HOME_POSE = [-0.14397, -0.43562, -0.19797, 0.001, -3.166, -0.040]
        # briefing.announce("Starting home pose.")
        # rtde_c.moveJ(HOME_POSE, 0.1, 0.2)
        # time.sleep(2.0)

        start_pose = rtde_r.getActualTCPPose()
        target_pose = list(start_pose)
        # waypoints = []
        #
        # p1 = list(start_pose);
        # p1[1] -= 0.05;
        # waypoints.append(p1)
        # p2 = list(p1);
        # p2[0] -= 0.05;
        # waypoints.append(p2)
        # p3 = list(p2);
        # p3[1] += 0.05;
        # waypoints.append(p3)
        # p4 = list(start_pose);
        # waypoints.append(p4)

        # print(f"Starting loop with {len(waypoints)} waypoints.")
        log_time("시작 tts 생성")
        briefing.announce("Starting sequence.")
        #time.sleep(2.0)
        briefing.wait_until_finished() #tts 끝날 때 까지 기다렸다가 동작 시작.
        total_moved_distance = 0.0
        last_pose = start_pose

        start_time = time.time()
        last_briefing_time = time.time()

        # 5. 이동 루프 시작
        # for i, target in enumerate(waypoints):
        #     print(f"[MOVE] Moving to Waypoint {i + 1}")
        #     rtde_c.moveL(target, ROBOT_SPEED, ROBOT_ACCEL, True)  # 비동기 이동
        #
        #     while True:
        #         curr_pose = rtde_r.getActualTCPPose()
        #
        #         # 거리 누적
        #         step_dist = get_distance(last_pose, curr_pose)
        #         total_moved_distance += step_dist
        #         last_pose = curr_pose
        #
        #         # ★ 주기적 브리핑 로직 (5초마다)
        #         current_time = time.time()
        #         if current_time - last_briefing_time >= BRIEFING_INTERVAL:
        #             elapsed = int(current_time - start_time)
        #             msg = f"Total moved {total_moved_distance:.2f} meters."
        #             briefing.announce(msg)
        #             last_briefing_time = current_time
        #
        #         if get_distance(curr_pose, target) < 0.001:
        #             break
        #
        #         time.sleep(0.05)
        #
        # rtde_c.stopL()
        #briefing.wait_until_finished()
        log_time("로봇 동작 시작")
        for i in range(100):
            if voice_system.is_triggered():
                print("비상 정지.")
                break
            target_pose[2] -= 0.005

            rtde_c.moveL(target_pose, ROBOT_SPEED, ROBOT_ACCEL, True)

            while True:
                if voice_system.is_triggered():
                    break
                curr_pose = rtde_r.getActualTCPPose()

                step_dist = get_distance(last_pose, curr_pose)
                total_moved_distance += step_dist
                last_pose = curr_pose

                current_time = time.time()
                if (current_time - last_briefing_time >= BRIEFING_INTERVAL) and (not briefing.is_speaking):
                    elapsed = int(current_time - start_time)
                    msg = f"Total moved {total_moved_distance:.2f} meters."
                    log_time("중간 tts 브리핑")
                    briefing.announce(msg)
                    last_briefing_time = current_time

                remaining_dist = get_distance(curr_pose, target_pose)
                if remaining_dist < 0.001:
                    break

                time.sleep(0.02)

            if voice_system.is_triggered():
                break

        rtde_c.stopL() #확인사살용 한번 더 명령 내림

        if voice_system.is_triggered():
            briefing.wait_until_finished()
            briefing.announce("Emergency stop.")
            log_time("비상 정지 tts 실행")
        else:
            final_msg = f"All tasks finished. Total distance moved is {total_moved_distance:.2f} meters."
            log_time("마지막 tts 출력")
            briefing.announce(final_msg)
        briefing.wait_until_finished()
        log_time("모든 tts 출력 완료")
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

if __name__ == "__main__":
    main()
