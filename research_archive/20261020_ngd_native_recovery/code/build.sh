#!/bin/bash
set -euo pipefail
export PATH=/usr/bin:/bin
unset CONDA_PREFIX CONDA_DEFAULT_ENV CMAKE_PREFIX_PATH PKG_CONFIG_PATH LD_LIBRARY_PATH
E=/media/wcqw/KESU/slam_research/ngd_native_recovery_20261020
D=/home/wcqw/ngd_native_recovery_20261020
export TMPDIR="$E/tmp"
OCV="$E/opencv-install/lib/cmake/opencv4"
cmake -S "$E/opencv-4.5.5" -B "$E/opencv-build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$E/opencv-install" -DBUILD_LIST=core,imgproc,imgcodecs,video,calib3d,features2d,dnn,highgui,videoio,flann -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_opencv_apps=OFF -DBUILD_JAVA=OFF -DBUILD_opencv_python2=OFF -DBUILD_opencv_python3=OFF -DWITH_IPP=OFF -DWITH_ITT=OFF -DWITH_CUDA=OFF -DWITH_OPENCL=OFF -DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DWITH_WEBP=OFF -DWITH_OPENEXR=OFF -DWITH_TIFF=OFF -DWITH_JASPER=OFF -DWITH_OPENJPEG=OFF -DWITH_QUIRC=OFF -DWITH_VTK=OFF -DWITH_LAPACK=OFF -DOPENCV_GENERATE_PKGCONFIG=ON > "$D/audit/opencv_configure_clean.log" 2>&1
/usr/bin/time -v cmake --build "$E/opencv-build" --parallel 4 > "$D/audit/opencv_build.log" 2>&1
cmake --install "$E/opencv-build" > "$D/audit/opencv_install.log" 2>&1
cmake -S "$E/NGD-SLAM/Thirdparty/DBoW2" -B "$E/dbow-build" -DCMAKE_BUILD_TYPE=Release -DOpenCV_DIR="$OCV" > "$D/audit/dbow_configure.log" 2>&1
/usr/bin/time -v cmake --build "$E/dbow-build" --parallel 2 > "$D/audit/dbow_build.log" 2>&1
cmake -S "$E/NGD-SLAM/Thirdparty/g2o" -B "$E/g2o-build" -DCMAKE_BUILD_TYPE=Release > "$D/audit/g2o_configure.log" 2>&1
/usr/bin/time -v cmake --build "$E/g2o-build" --parallel 2 > "$D/audit/g2o_build.log" 2>&1
cmake -S "$E/NGD-SLAM" -B "$E/ngd-build" -DCMAKE_BUILD_TYPE=Release -DOpenCV_DIR="$OCV" -DPangolin_DIR=/home/wcqw/passive_visual_slam_qualification_20261015/local/lib/cmake/Pangolin > "$D/audit/ngd_configure.log" 2>&1
/usr/bin/time -v cmake --build "$E/ngd-build" --target rgbd_tum --parallel 2 > "$D/audit/ngd_build.log" 2>&1
(cd "$E/NGD-SLAM/Vocabulary" && tar -xf ORBvoc.txt.tar.gz)
echo 'OpenCV, DBoW2, native NGD RGB-D build complete'
