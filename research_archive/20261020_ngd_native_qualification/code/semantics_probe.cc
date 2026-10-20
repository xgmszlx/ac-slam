// Language semantics only. Not a detector, SLAM run, or algorithm improvement.
#include <cmath>
#include <iostream>
#include <cassert>
int main(){
 std::cout<<"SOFTWARE_SEMANTICS_ONLY\nroll_deg,source_abs_comparison,magnitude_comparison\n";
 for(double a: {-20.,-10.,-5.,0.,5.,10.,20.}){
  bool original=std::abs(a>10);bool magnitude=std::abs(a)>10;
  std::cout<<a<<","<<original<<","<<magnitude<<"\n";
  if(a==-20)assert(!original&&magnitude);
 }
 std::cout<<"mask_pixels,total_pixels,clear_predicate\n";
 for(int n: {245759,245760,245761}){bool clear=(double)n/307200>.8;std::cout<<n<<",307200,"<<clear<<"\n";if(n==245760)assert(!clear);if(n==245761)assert(clear);}
}
