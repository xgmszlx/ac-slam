#pragma once
#include <opencv2/opencv.hpp>
// One predeclared rule; zeros are invalid, not an extra surface. No dilation.
inline cv::Mat depthBoundary(const cv::Mat &raw){
 CV_Assert(raw.type()==CV_16UC1);
 cv::Mat valid=raw>0, mnInput=raw.clone(),lo,hi,count,ones;
 mnInput.setTo(65535,~valid);
 cv::erode(mnInput,lo,cv::Mat(),cv::Point(-1,-1),1,cv::BORDER_CONSTANT,cv::Scalar(65535));
 cv::dilate(raw,hi,cv::Mat(),cv::Point(-1,-1),1,cv::BORDER_CONSTANT,cv::Scalar(0));
 valid.convertTo(ones,CV_32F,1.0/255.0);cv::boxFilter(ones,count,CV_32F,cv::Size(3,3),cv::Point(-1,-1),false,cv::BORDER_CONSTANT);
 cv::Mat mask=cv::Mat::zeros(raw.size(),CV_8U);
 for(int y=0;y<raw.rows;++y)for(int x=0;x<raw.cols;++x){
  unsigned short d=raw.at<unsigned short>(y,x);
  if(d>0 && count.at<float>(y,x)>=2.f && (int(hi.at<unsigned short>(y,x))-int(lo.at<unsigned short>(y,x)))>std::max(250.0,.03*d))mask.at<unsigned char>(y,x)=255;
 }
 return mask;
}
