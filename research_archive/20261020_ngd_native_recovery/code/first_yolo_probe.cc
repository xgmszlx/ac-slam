#include "YOLO.h"
#include <opencv2/imgcodecs.hpp>
int main(int argc,char **argv){
 if(argc!=3)return 2;
 std::cout<<"OpenCV "<<CV_VERSION<<" threads "<<cv::getNumThreads()<<std::endl;
 auto rgb=cv::imread(argv[1],cv::IMREAD_UNCHANGED);auto raw=cv::imread(argv[2],cv::IMREAD_UNCHANGED);cv::Mat depth;raw.convertTo(depth,CV_32F,1.0/5000.0);
 ORB_SLAM3::YOLO y(.5,.4,320,320,"./Thirdparty/YOLO/coco.names","./Thirdparty/YOLO/yolo-fastest-xl.cfg","./Thirdparty/YOLO/yolo-fastest-xl.weights","yolo-fastest");
 auto mask=y.Detect(rgb,depth,0);
 std::cout<<"Author Detect PASS; mask "<<mask.cols<<"x"<<mask.rows<<" nonzero "<<cv::countNonZero(mask)<<std::endl;
}
