#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "amcl/pf/pf.h"
static int random_calls=0;
static pf_vector_t random_pose(void *unused) {
 pf_vector_t v; ++random_calls;
 v.v[0]=drand48()*10-5; v.v[1]=drand48()*10-5; v.v[2]=drand48()*6.28-3.14; return v;
}
static double sensor(void *data,pf_sample_set_t *set) {
 int step=*(int*)data;double total=0;
 double scale=step<3?1.:((step%3==0)?1e-30:1e-10);
 for(int i=0;i<set->sample_count;i++) {
  double x=set->samples[i].pose.v[0]-.1*step;
  set->samples[i].weight *= scale*exp(-x*x/2.);
  total+=set->samples[i].weight;
 }
 return total;
}
static double zero_sensor(void *data,pf_sample_set_t *set) {
 for(int i=0;i<set->sample_count;i++)set->samples[i].weight=0.;return 0.;
}
int main(int argc,char **argv) {
 int on=atoi(argv[1]);setenv("AMCL_EXPERIMENT_SEED","1702",1);
 pf_t *pf=pf_alloc(100,1000,on?.001:0.,on?.1:0.,random_pose,NULL);
 pf_vector_t mean=pf_vector_zero();pf_matrix_t cov=pf_matrix_zero();
 cov.m[0][0]=cov.m[1][1]=.04;cov.m[2][2]=.03;
 pf_init(pf,mean,cov);
 for(int step=0;step<12;step++) {
  pf_update_sensor(pf,sensor,&step); pf_update_resample(pf);
  pf_sample_set_t *s=pf->sets+pf->current_set;
  printf("%d %d %.17g %.17g %d %.17g\n",step,s->sample_count,pf->w_slow,pf->w_fast,random_calls,drand48());
  for(int i=0;i<s->sample_count;i++)printf("%.17g %.17g %.17g %.17g\n",s->samples[i].pose.v[0],s->samples[i].pose.v[1],s->samples[i].pose.v[2],s->samples[i].weight);
 }
 pf_update_sensor(pf,zero_sensor,NULL);
 printf("zero %.17g %.17g\n",pf->sets[pf->current_set].n_effective,drand48());
 pf_free(pf);return 0;
}
