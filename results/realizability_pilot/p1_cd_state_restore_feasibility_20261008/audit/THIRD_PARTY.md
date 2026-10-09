# Third-party audit material

`rospy_publisher_source.txt` contains the installed ROS Noetic `_PublisherImpl.publish` function from `ros_comm/clients/rospy/src/rospy/topics.py`, copyright 2008 Willow Garage, Inc., BSD 3-clause. Its copyright, conditions and disclaimer are retained at the top of the snapshot. Upstream: <https://github.com/ros/ros_comm/blob/noetic-devel/clients/rospy/src/rospy/topics.py>. The exact installed module SHA is in `publisher_failure.json`.

`observation.patch` is an observation-only diff against Steve Macenski's ROS 1 `slam_toolbox` 1.5.7 and its bundled Karto SDK. No full upstream repository or binary is republished here. Original source/license notices remain in the independent source tree; package metadata identifies LGPL, and historical file headers must also be retained. Pinned upstream: <https://github.com/SteveMacenski/slam_toolbox/tree/1.5.7>.

`isolation_dependency.patch` changes one generated Ceres CMake imported-library path in an independently extracted Ubuntu dependency package. Dependency package versions and hashes are retained in the build manifest. These audit snapshots do not claim authorship of upstream code.
