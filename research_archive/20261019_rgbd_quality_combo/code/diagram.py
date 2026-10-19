from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parents[1]
fig,ax=plt.subplots(figsize=(12,6.5));ax.set(xlim=(0,12),ylim=(0,7));ax.axis('off')
def box(x,y,text,c='#eef4fa',w=3.1):ax.text(x,y,text,ha='center',va='center',fontsize=10,bbox=dict(boxstyle='round,pad=.6',fc=c,ec='#40566e'))
def arrow(a,b):ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',lw=1.4,color='#40566e'))
box(5.8,6.4,'Native ORB keypoints + descriptors\nRGB unchanged',w=3.8)
box(1.8,4.9,'S0: no frontend action\nNative RGB-D processing');arrow((4.8,6),(2,5.4))
box(6.5,4.9,'S1/S2: matched 2D checks\nMutual ratio + forward/backward LK');arrow((6.2,6),(6.5,5.5))
box(10.2,4.9,'Bad matched 2D:\nreject in both',c='#fde8df');arrow((8.2,4.9),(9.1,4.9))
box(6.5,3.2,'Common camera compensation\nPnP-RANSAC, no GT');arrow((6.5,4.3),(6.5,3.8))
box(3.1,1.65,'S1: 3D residual > 0.05m\nreject that feature',c='#fde8df');arrow((5.2,2.9),(3.3,2.2))
box(9,1.65,'S2: reliable depth -> S1 rule\nUnreliable depth + good 2D:\nkeep 2D, invalidate depth',c='#e5f3e7');arrow((7.8,2.9),(8.8,2.3))
box(6,.25,'Same native map / pose optimizer / evaluation; no new objective or kernel',c='#f0f0f0');arrow((3.1,1.1),(4.5,.65));arrow((9,1.0),(7.5,.65));arrow((1.8,4.25),(1.8,.25));arrow((1.8,.25),(3.0,.25))
fig.suptitle('Prototype decision flow — software tested, Bonn runs NOT EXECUTED',fontsize=14)
fig.text(.02,.01,'Unmatched or no-qualified-pose cases remain native/unassessed. Fallback is not a static label or an automatic new MapPoint.',fontsize=9)
fig.savefig(P/'figures/observation_processing.png',dpi=160,bbox_inches='tight')
