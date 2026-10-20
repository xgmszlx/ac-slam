# Technical recovery reproduction

This archive records a failed baseline qualification, not successful NGD trajectory reproduction. Do not automatically rerun its entry scripts: both runtime attempts are closed.

Fixed author: https://github.com/yuhaozhang7/NGD-SLAM/tree/a93a14c4019efc7a209be5fbf9fefa46f5d1d90f . Inputs are user-provided official NGD ZIP and OpenCV4.5.5 source tar, locally hashed in audit. All 428 extracted necessary files match the previously acquired fixed Git tree. OpenCV source expanded on external KESU; no system installation.

`code/prepare.py` documents one-time source extraction; it refuses overwriting already extracted NGD members. The initial metadata writer used a closed TarFile after extraction; metadata was completed by reopening headers, without re-extraction. Native CMake also required Examples_old sources, which were subsequently extracted unchanged. g2o must be built before the native target, as in the author script. These preparation/order failures are retained; none changed estimator source.

`code/build.sh` is the corrected sequential build recipe. It clears Conda/ROS lookup environment and installs OpenCV privately, with 4 build jobs; dependencies/NGD use2. It uses only supplied sources and system dependencies. No unrestricted author make -j is executed. OpenCV optional IPP/ITT/CUDA/OpenCL/FFmpeg/GStreamer/OpenJPEG/VTK/LAPACK and tests/examples/Python/Java are disabled. The selected modules include core/imgproc/imgcodecs/video/videoio/features2d/flann/calib3d/highgui/dnn. `OpenCV_DIR` is the private `opencv-install/lib/cmake/opencv4` for both DBoW2 and NGD.

`code/build_headless.py` uses the exact author-example compile/link flags to build an independent entry with only viewer=false; original rgbd_tum and NGD library remain unchanged. The patch is in audit. Vocabulary is extracted on KESU from the supplied Git-verified archive. Source/binary hashes were frozen before both starts. No core/mask/state hooks were compiled.

`runtime_probe.cc` checks original cfg/weights forward compatibility using the first real RGB. `first_yolo_probe.cc` separately calls unmodified author YOLO::Detect on that image and registered float depth under `OPENCV_FOR_THREADS_NUM=1`. These are software preflights, not SLAM runs or motion-accuracy tests. `linkage.py` checks both entry binaries, DBoW2 and NGD dependencies. Saved process maps verify the same runtime OpenCV origin.

`check_inputs.py` uses existing system Python/OpenCV to decode and hash all827 input pairs. TUM3_BGR.yaml differs from author's RGB-D TUM3.yaml only in Camera.RGB=0, matching imread BGR. GT is not passed to SLAM. `evaluate.py` copies the prior frozen SE3 scale1 /1sRPE/20msGT/100ms-gap evaluator; only plot legend names were changed. It was not run because no trajectory exists.

`run_one.py` and `run_retry.py` have existing-directory guards, record hashes before subprocess launch and preserve outputs/status. The initial launcher import used zoneinfo unavailable in system Python3.8 and failed before creating a run; this was replaced by the standard-library UTC+8 timezone. This is not an additional SLAM start. Runtime cwd must be the isolated NGD source root because the author hardcodes model paths relative to it. All temporary/cache/build files use KESU. The retry differs only by OpenCV thread environment and its output/registration path.

The two GDB prefix starts are separately disclosed in REPORT. First stopped too early at the PLT/entry; corrected version stopped on first-frame SIGBUS in original YOLO postprocessing. No source was instrumented or rebuilt for GDB. There was no GDB replay of walking02, no new complete trajectory, and no repair of the connected-component primitive.

`code/finalize.py` verifies unchanged author/old files, runtime OpenCV maps and summarizes both real failures. Runtime summaries and source hashes are preserved in results/audit/protocol. `resource.txt`'s final Exit status line must not override its signal11 line and the recorded wrapper return139.

Publication compresses build/GDB logs losslessly as .log.gz; raw originals remain in the independent local directory. It excludes supplied archives, all RGB-D/GT, vocabulary, weights, compiled objects/libraries and cache directories. Remote SHA is verified after push and stored only in local PUBLISHED.json.

Publication review found a launcher path replacement bug: the retry overwrote first_run_frozen.json and attempts_final.json with walking02 records. Both actual files are retained, also copied to explicit retry filenames. The initial registration is clearly labeled reconstructed from walking01 started/run records and unchanged artifacts; its original bytes did not survive. No stdout/resource/run/started records or old research files were overwritten. The retry launcher paths have been corrected without another execution.

Scoped .gitattributes retains verbatim author-example, patch-context and log end-of-line spaces; normal whitespace checking remains enabled for the new analysis/build scripts.
