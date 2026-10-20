#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <fstream>
#include <iostream>
#include <deque>
#include <vector>
#include <string>
using namespace cv;
Mat maskcase(std::string s){
 Mat m=Mat::zeros(s=="zero480"?480:(s=="zero10"||s=="diag10"?10:80),s=="zero480"?640:(s=="zero10"||s=="diag10"?10:100),CV_8UC1);
 if(s=="diag10"){for(int i=0;i<10;i++)m.at<uchar>(i,i)=1;}
 if(s=="rects"){rectangle(m,Rect(4,5,11,17),Scalar(1),FILLED);rectangle(m,Rect(40,20,19,29),Scalar(1),FILLED);m.at<uchar>(70,90)=1;}
 if(s=="tie"){rectangle(m,Rect(60,3,10,10),Scalar(1),FILLED);rectangle(m,Rect(4,50,10,10),Scalar(1),FILLED);}
 if(s=="edge"){rectangle(m,Rect(0,0,10,30),Scalar(1),FILLED);rectangle(m,Rect(10,30,10,10),Scalar(1),FILLED);rectangle(m,Rect(90,70,10,10),Scalar(1),FILLED);}
 return m;
}
Mat bfs(const Mat&m,int &n){Mat l=Mat::zeros(m.size(),CV_32S);n=0;int dx[]={1,-1,0,0},dy[]={0,0,1,-1};for(int y=0;y<m.rows;y++)for(int x=0;x<m.cols;x++)if(m.at<uchar>(y,x)&&!l.at<int>(y,x)){++n;std::deque<Point>q;q.emplace_back(x,y);l.at<int>(y,x)=n;while(!q.empty()){Point a=q.front();q.pop_front();for(int k=0;k<4;k++){int u=a.x+dx[k],v=a.y+dy[k];if(u>=0&&u<m.cols&&v>=0&&v<m.rows&&m.at<uchar>(v,u)&&!l.at<int>(v,u)){l.at<int>(v,u)=n;q.emplace_back(u,v);}}}}return l;}
void save(std::string p,const Mat&m){std::ofstream f(p,std::ios::binary);for(int y=0;y<m.rows;y++)f.write((const char*)m.ptr(y),m.cols*m.elemSize());}
Mat finalmask(Mat m){Mat o;dilate(m,o,getStructuringElement(MORPH_RECT,Size(7,7)));if((double)countNonZero(o)/o.total()>.8)o=Mat::zeros(o.size(),CV_8U);return o;}
int main(int argc,char**argv){if(argc!=5)return 2;std::string alg=argv[1],name=argv[2],prefix=argv[4];setNumThreads(std::stoi(argv[3]));Mat m=maskcase(name);std::cout<<"OpenCV "<<CV_VERSION<<" threads "<<getNumThreads()<<" case "<<name<<" alg "<<alg<<std::endl;Mat l,s,c;int n;
 if(alg=="default")n=connectedComponentsWithStats(m,l,s,c,4,CV_32S);else n=connectedComponentsWithStats(m,l,s,c,4,CV_32S,CCL_SAUF);
 int nr=0;Mat ref=bfs(m,nr),canon=Mat::zeros(m.size(),CV_32S);std::vector<int> map(n,0);int next=0;
 for(int y=0;y<m.rows;y++)for(int x=0;x<m.cols;x++)if(m.at<uchar>(y,x)){int v=l.at<int>(y,x);if(v<=0||v>=n)return 3;if(!map[v])map[v]=++next;canon.at<int>(y,x)=map[v];}
 bool partitions=n==nr+1 && countNonZero(canon!=ref)==0;int largest=0,area=0;for(int i=1;i<n;i++)if(s.at<int>(i,CC_STAT_AREA)>area){largest=i;area=s.at<int>(i,CC_STAT_AREA);}Mat largestMask;compare(l,largest,largestMask,CMP_EQ);largestMask/=255;Mat final=finalmask(largestMask);
 int refBest=0,refArea=0;for(int i=1;i<=nr;i++){int a=countNonZero(ref==i);if(a>refArea){refArea=a;refBest=i;}}Mat refMax;compare(ref,refBest,refMax,CMP_EQ);refMax/=255;
 save(prefix+".partition",canon);save(prefix+".max",largestMask);save(prefix+".final",final);
 std::ofstream f(prefix+".json");f<<"{\"components\":"<<n<<",\"reference_components\":"<<nr+1<<",\"partition_equal_bfs\":"<<(partitions?"true":"false")<<",\"largest_equal_bfs_rowmajor\":"<<(countNonZero(largestMask!=refMax)==0?"true":"false")<<",\"final_equal_bfs_rowmajor\":"<<(countNonZero(final!=finalmask(refMax))==0?"true":"false")<<",\"largest_foreground_area\":"<<area<<"}";
 std::cout<<"components "<<n<<" BFS_equal "<<partitions<<std::endl;return partitions?0:4;
}
