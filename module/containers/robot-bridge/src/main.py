"""robot-bridge 컨테이너 진입점 (뼈대)

로봇 제조사의 ROS2 토픽(정차 상태, 위치)을 구독해 RobotState 로 바꿔 core에 전달한다.
토픽 이름은 협력 로봇 제조사 인터페이스가 정해지면 확정한다.
"""


def main():
    # TODO: rclpy 노드 생성 → 제조사 토픽 구독 → RobotState 전송
    raise NotImplementedError("robot-bridge 구현 예정")


if __name__ == "__main__":
    main()
