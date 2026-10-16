"""Exact installed Keras factory graph; omit only redundant ImageNet init I/O.

The complete custom author H5 must overwrite every model variable afterwards.
This module does not assign, reshape, skip or remap any checkpoint array.
"""
import ast,copy,hashlib,inspect,json
from pathlib import Path
from keras.src.applications import efficientnet


def build_author_base(root):
    source=inspect.getsource(efficientnet.EfficientNet)
    tree=ast.parse(source);function=tree.body[0]
    matches=[]
    for node in function.body:
        if isinstance(node,ast.If) and any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
                                        and x.func.attr=='get_file' for x in ast.walk(node)):
            matches.append(node)
    assert len(matches)==1
    removed=matches[0]
    # The omitted final branch performs only path construction/download/loading.
    # No forward tensor assignment or layer construction is allowed in it.
    assert not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)
                   and isinstance(x.func.value,ast.Name) and x.func.value.id=='layers' for x in ast.walk(removed))
    assert any(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='load_weights'
               for x in ast.walk(removed))
    function.body=[node for node in function.body if node is not removed]
    clean_expected=copy.deepcopy(ast.parse(source))
    clean_expected.body[0].body=[n for n in clean_expected.body[0].body
                               if ast.dump(n)!=ast.dump(removed)]
    assert ast.dump(tree)==ast.dump(clean_expected)
    scope=dict(efficientnet.__dict__)
    exec(compile(ast.fix_missing_locations(tree),'<author factory without initial I/O>','exec'),scope)
    wrapper=ast.parse(inspect.getsource(efficientnet.EfficientNetB1))
    wrapper.body[0].decorator_list=[] # Export metadata only, no duplicate registration.
    exec(compile(ast.fix_missing_locations(wrapper),'<unchanged EfficientNetB1 arguments>','exec'),scope)
    base=scope['EfficientNetB1'](input_shape=(500,500,3),include_top=False,weights='imagenet')
    scales=[l.get_config()['scale'] for l in base.layers if type(l).__name__=='Rescaling']
    assert len(scales)==2,scales
    out={'scope':'Only final initialization download/load branch omitted; entire forward factory AST retained',
         'original_factory_sha256':hashlib.sha256(source.encode()).hexdigest(),
         'removed_statement_ast':ast.dump(removed),'forward_AST_preserved':True,
         'original_EfficientNetB1_arguments_preserved':True,'rescaling_layers':scales,
         'required_followup':'Standard full author H5 load plus equality of every model variable',
         'no_manual_weight_mapping':True}
    (Path(root)/'audit/forward_graph_extraction.json').write_text(json.dumps(out,indent=2))
    return base
