#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/dnn.hpp>
#include <iostream>
int main(int argc,char**argv){
 if(argc!=4)return 2;
 std::cout<<"OpenCV "<<CV_VERSION<<"\n"<<cv::getBuildInformation()<<std::endl;
 cv::Mat im=cv::imread(argv[3],cv::IMREAD_COLOR);if(im.empty())return 3;
 cv::dnn::Net n=cv::dnn::readNetFromDarknet(argv[1],argv[2]);
 n.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);n.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);
 cv::Mat b;cv::dnn::blobFromImage(im,b,1/255.0,cv::Size(320,320),cv::Scalar(0,0,0),true,false);n.setInput(b);
 std::vector<cv::Mat> out;n.forward(out,n.getUnconnectedOutLayersNames());
 std::cout<<"CPU DNN forward outputs "<<out.size()<<std::endl;
 for(const auto &m:out){if(!cv::checkRange(m))return 4;std::cout<<"output "<<m.rows<<" x "<<m.cols<<std::endl;}
 return 0;
}
