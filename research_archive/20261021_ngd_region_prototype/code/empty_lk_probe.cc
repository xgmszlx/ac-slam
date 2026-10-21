#include <opencv2/core.hpp>
#include <opencv2/video/tracking.hpp>
#include <iostream>
int main(){cv::Mat a(80,100,CV_8U,cv::Scalar(0));std::vector<cv::Point2f>x,y;std::vector<uchar>s;std::vector<float>e;std::cout<<CV_VERSION<<std::endl;try{cv::calcOpticalFlowPyrLK(a,a,x,y,s,e);std::cout<<"NO_EXCEPTION"<<std::endl;return 1;}catch(const cv::Exception&v){std::cout<<"NATIVE_EMPTY_LK_THROWS\n"<<v.what()<<std::endl;return 0;}}
