import time
import math
import sys

# ★ 분리한 TTS 모듈 불러오기
from src.briefing import BriefingSystem

# UR 제어 라이브러리
from rtde_control import RTDEControlInterface
from rtde_receive import RTDEReceiveInterface

# ================= 설정 =================
ROBOT_IP = "192.168.0.61"
ROBOT_SPEED = 0.025
ROBOT_ACCEL = 0.1
BRIEFING_INTERVAL = 3.0  # 5초마다 보고


# =======================================

def get_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)


def main():
    # 1. 브리핑 시스템 초기화
    briefing = BriefingSystem()

    # 2. 로봇 연결
    print(f"[ROBOT] Connecting to {ROBOT_IP}...")
    try:
        rtde_c = RTDEControlInterface(ROBOT_IP)
        rtde_r = RTDEReceiveInterface(ROBOT_IP)
        print("[ROBOT] Connection Successful!")
    except Exception as e:
        print(f"[ROBOT ERROR] 연결 실패: {e}")
        sys.exit(1)

    try:
        #HOME_POSE = [-143.97, -435.62, -197.97, 0.001, -3.166, -0.040]
        #briefing.announce("Starting home pose.")
        #rtde_c.moveJ(HOME_POSE, 0.1, 0.2)
        time.sleep(2.0)

        start_pose = rtde_r.getActualTCPPose()
        waypoints = []

        # 웨이포인트 1~4 생성
        p1 = list(start_pose);
        p1[1] -= 0.05;
        waypoints.append(p1)
        p2 = list(p1);
        p2[0] -= 0.05;
        waypoints.append(p2)
        p3 = list(p2);
        p3[1] += 0.05;
        waypoints.append(p3)
        p4 = list(start_pose);
        waypoints.append(p4)

        print(f"Starting loop with {len(waypoints)} waypoints.")
        briefing.announce("Starting sequence.")
        time.sleep(2.0)

        # 4. 변수 초기화
        total_moved_distance = 0.0
        last_pose = start_pose

        start_time = time.time()
        last_briefing_time = time.time()

        # 5. 이동 루프 시작
        for i, target in enumerate(waypoints):
            print(f"[MOVE] Moving to Waypoint {i + 1}")
            rtde_c.moveL(target, ROBOT_SPEED, ROBOT_ACCEL, True)  # 비동기 이동

            # 이동 중 감시 루프
            while True:
                curr_pose = rtde_r.getActualTCPPose()

                # 거리 누적
                step_dist = get_distance(last_pose, curr_pose)
                total_moved_distance += step_dist
                last_pose = curr_pose

                # ★ 주기적 브리핑 로직 (5초마다)
                current_time = time.time()
                if current_time - last_briefing_time >= BRIEFING_INTERVAL:
                    elapsed = int(current_time - start_time)
                    msg = f"Total moved {total_moved_distance:.2f} meters."
                    briefing.announce(msg)
                    last_briefing_time = current_time

                # 도착 체크
                if get_distance(curr_pose, target) < 0.001:
                    break

                time.sleep(0.05)

        rtde_c.stopL()

        # 6. 최종 완료
        final_msg = f"All tasks finished. Total distance moved is {total_moved_distance:.2f} meters."
        briefing.announce(final_msg)

        # 프로그램 종료 전 말이 끝날 때까지 대기 (깔끔해진 호출)
        briefing.wait_until_finished()

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