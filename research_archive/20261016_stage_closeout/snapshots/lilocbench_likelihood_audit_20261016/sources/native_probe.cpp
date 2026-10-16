// Offline function-call probe only. No ROS node, PF run, map or source modification.
#include <cmath>
#include <cstdlib>
#include <limits>
#include <map_server/image_loader.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/utils.h>
#include <amcl/map/map.h>
// Access control only for testing the already-built native static model functions.
#define private public
#include <amcl/sensors/amcl_laser.h>
#undef private
using namespace amcl;
extern "C" {
map_t* probe_map(const char* image) {
 nav_msgs::GetMap::Response response;double origin[3]={-25.,-25.,0.};
 map_server::loadMapFromFile(&response,image,.05,false,.65,.196,origin,TRINARY);
 const auto& msg=response.map;map_t* m=map_alloc();m->size_x=msg.info.width;m->size_y=msg.info.height;
 m->scale=msg.info.resolution;m->origin_x=msg.info.origin.position.x+(m->size_x/2)*m->scale;m->origin_y=msg.info.origin.position.y+(m->size_y/2)*m->scale;
 m->cells=(map_cell_t*)malloc(sizeof(map_cell_t)*m->size_x*m->size_y);
 for(int i=0;i<m->size_x*m->size_y;++i)m->cells[i].occ_state=msg.data[i]==0?-1:(msg.data[i]==100?1:0);
 map_update_cspace(m,2.);return m;
}
void probe_arrays(map_t* m,int* state,double* distances,double* metadata){
 metadata[0]=m->size_x;metadata[1]=m->size_y;metadata[2]=m->scale;metadata[3]=m->origin_x;metadata[4]=m->origin_y;
 for(int i=0;i<m->size_x*m->size_y;++i){state[i]=m->cells[i].occ_state;distances[i]=m->cells[i].occ_dist;}
}
int probe_size(map_t* m){return m->size_x*m->size_y;}
void probe_prepare(int n,const float* input,float rmin,float rmax,float amin,float ainc,const double* quat,double* ranges,double* bearings){
 tf2::Quaternion ext(quat[0],quat[1],quat[2],quat[3]),q;
 q.setRPY(0.,0.,amin);double mn=tf2::getYaw(ext*q);
 q.setRPY(0.,0.,amin+ainc);double inc=tf2::getYaw(ext*q)-mn;
 inc=fmod(inc+5*M_PI,2*M_PI)-M_PI;
 for(int i=0;i<n;++i){ranges[i]=input[i]<=rmin?rmax:(input[i]>rmax?std::numeric_limits<double>::max():input[i]);bearings[i]=mn+i*inc;}
}
double probe_score(map_t* m,int model,int max_beams,int n,const double* ranges,const double* bearings,double rmax,const double* base,const double* laser){
 AMCLLaser sensor(max_beams,m);
 if(model==0)sensor.SetModelLikelihoodField(.95,.05,.2,2.);
 else sensor.SetModelLikelihoodFieldProb(.95,.05,.2,2.,false,.5,.3,.9);
 pf_vector_t lp=pf_vector_zero();lp.v[0]=laser[0];lp.v[1]=laser[1];sensor.SetLaserPose(lp);
 AMCLLaserData data;data.sensor=&sensor;data.range_count=n;data.range_max=rmax;data.ranges=new double[n][2];
 for(int i=0;i<n;++i){data.ranges[i][0]=ranges[i];data.ranges[i][1]=bearings[i];}
 pf_sample_t sample;for(int i=0;i<3;++i)sample.pose.v[i]=base[i];sample.weight=1.;
 pf_sample_set_t set={};set.sample_count=1;set.samples=&sample;set.converged=0;
 return model==0?AMCLLaser::LikelihoodFieldModel(&data,&set):AMCLLaser::LikelihoodFieldModelProb(&data,&set);
}
}
