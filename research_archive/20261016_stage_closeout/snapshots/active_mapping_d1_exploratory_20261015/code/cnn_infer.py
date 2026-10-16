"""Strict frozen checkpoint qualification, CPU only. No training, GT or ROS."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='-1'
from pathlib import Path
import hashlib,json,resource,time,traceback
import numpy as np
import tensorflow as tf
import h5py
R=Path(__file__).resolve().parents[1]


def decode(x):return x.decode() if isinstance(x,bytes) else str(x)


def main():
    out=R/'results/phase0_qualified_extraction.json'
    assert not out.exists()
    tf.config.set_visible_devices([],'GPU');tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
    start=time.monotonic()
    tf.random.set_seed(1234)
    from author_model_factory import build_author_base
    base=build_author_base(R)
    for layer in base.layers[:200]:layer.trainable=False
    model=tf.keras.Sequential([base,tf.keras.layers.Conv2D(1280,1,padding='same',activation='relu'),
                              tf.keras.layers.GlobalAveragePooling2D(),tf.keras.layers.Dropout(.4),tf.keras.layers.Dense(2,activation='softmax')])
    model.build((None,500,500,3))
    (R/'audit/author_constructor_layers.json').write_text(json.dumps([{'name':l.name,'type':type(l).__name__,'config':l.get_config()} for l in base.layers],indent=2,default=str))
    weights=R/'sources/author/Code/checkpoint_weights/weights_classification/weights_old.h5'
    model.load_weights(str(weights))
    # Independently compare every saved array, including non-trainable BN statistics.
    mapping=[]
    with h5py.File(weights,'r') as h:
        groups=[h[decode(name)] for name in h.attrs['layer_names'] if len(h[decode(name)].attrs.get('weight_names',[]))]
        layers=[layer for layer in model.layers if layer.weights]
        assert len(groups)==len(layers)
        for group,layer in zip(groups,layers):
            names=list(group.attrs['weight_names']);variables=layer.trainable_weights+layer.non_trainable_weights
            assert len(names)==len(variables),(group.name,len(names),len(variables))
            for name,var in zip(names,variables):
                a=np.asarray(group[decode(name)]);b=var.numpy()
                assert a.shape==b.shape and np.array_equal(a,b),(decode(name),var.name,a.shape,b.shape)
                assert np.all(np.isfinite(b)),var.name
                mapping.append({'h5':group.name+'/'+decode(name),'model':var.name,'shape':list(a.shape),'equal':True})
    assert len(mapping)==len(model.weights)
    (R/'audit/loaded_weights.json').write_text(json.dumps(mapping,indent=2))
    build_load=time.monotonic()-start;manifest=json.loads((R/'data/cnn_inputs_manifest.json').read_text());predictions=[]
    first=None
    for row in manifest:
        image=tf.keras.preprocessing.image.load_img(str(R/row['path']),color_mode='rgb',target_size=(500,500),interpolation='nearest')
        array=tf.keras.preprocessing.image.img_to_array(image)
        processed=tf.keras.applications.efficientnet.preprocess_input(array.copy())
        assert np.array_equal(array,processed),'Unexpected extra normalization'
        t=time.monotonic();p=model(processed[None,...],training=False).numpy()[0];elapsed=time.monotonic()-t
        assert np.all(np.isfinite(p)) and abs(float(p.sum())-1)<1e-5
        predictions.append(dict(row,p_NOT_EX=float(p[0]),p_EX=float(p[1]),stop_at_08=bool(p[1]>=.8),wall_s=elapsed))
        if first is None:first=processed
    warm=[]
    for _ in range(5):
        t=time.monotonic();model(first[None,...],training=False).numpy();warm.append(time.monotonic()-t)
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    result={'status':'PASS' if peak<=4*1024**3 else 'RESOURCE_QUALIFICATION_FAIL',
            'tensorflow':tf.__version__,'keras':getattr(tf.keras,'__version__','bundled'),
            'weight_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),'arrays_loaded_and_equal':len(mapping),
            'all_model_weights_accounted_for':True,'model_parameters':model.count_params(),'build_load_s':build_load,
            'peak_rss_bytes':peak,'warm_times_s':warm,'predictions':predictions,
            'class_order':['NOT_EXPLORED','EXPLORED'],'extra_rescale':False,'model_inference_only':True,
            'limits':['Four author raw inputs are not the published FP subset','Stage inputs are final maps, not a continuous stopping sequence',
                      'Inference qualification is not scientific action value or proof of calibration']}
    out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:
        (R/('failures/phase0_'+os.environ.get('D1_ATTEMPT_ID','unknown')+'.json')).write_text(json.dumps({'status':'TECHNICAL_INCOMPLETE','error':repr(error),'traceback':traceback.format_exc(),'ROS_allowed':False},indent=2))
        raise
