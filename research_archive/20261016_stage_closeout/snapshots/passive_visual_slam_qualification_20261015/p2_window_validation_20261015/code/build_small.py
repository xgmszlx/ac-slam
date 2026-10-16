import pathlib,shlex,subprocess,os,sys,json
N=pathlib.Path(__file__).resolve().parents[1];O=N.parent;S=O/'sources/ORB_SLAM3-4452a3c4ab75b1cde34e5505a36ec3f9edcdc4c4';B=S/'build'
flags=(B/'CMakeFiles/rgbd_tum_headless.dir/flags.make').read_text();f={l.split(' = ')[0]:l.split(' = ')[1] for l in flags.splitlines() if ' = ' in l}
def compile(source,name,extra=()):
 obj=N/'build'/(name+'.o');binary=N/'build'/name
 cmd=['/usr/bin/c++']+list(extra)+shlex.split(f['CXX_DEFINES'])+shlex.split(f['CXX_INCLUDES'])+shlex.split(f['CXX_FLAGS'])+['-UNDEBUG','-c',str(source),'-o',str(obj)]
 link=shlex.split((B/'CMakeFiles/rgbd_tum_headless.dir/link.txt').read_text());link[link.index('CMakeFiles/rgbd_tum_headless.dir/Examples/RGB-D/rgbd_tum_headless.cc.o')]=str(obj);link[link.index('-o')+1]=str(binary)
 with (N/'audit'/('build_'+name+'.log')).open('w') as log:
  subprocess.run(cmd,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True);subprocess.run(link,cwd=B,stdout=log,stderr=subprocess.STDOUT,check=True)
 return binary
if __name__=='__main__':
 binary=compile(N/'code/raw_features.cc','raw_features');D=O/'data/rgbd_dataset_freiburg3_walking_xyz';env=os.environ.copy();env['LD_LIBRARY_PATH']=str(S/'lib')+':'+str(O/'local/lib')+':'+env.get('LD_LIBRARY_PATH','')
 r=subprocess.run([str(binary),str(D),str(D/'associations.txt'),str(N/'results/raw_ORB_features.csv')],cwd=N,env=env);assert r.returncode==0
 print('raw ORB extraction only, not tracked matches/inliers')
