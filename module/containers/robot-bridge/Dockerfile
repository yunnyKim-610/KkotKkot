# robot-bridge: 로봇 본체와 ROS2 통신. ROS2는 이 컨테이너 안에만 둔다
FROM ros:humble-ros-base
WORKDIR /app
COPY shared /app/shared
COPY containers/robot-bridge/src /app/src
CMD ["bash", "-c", "source /opt/ros/humble/setup.bash && python3 -m src.main"]
