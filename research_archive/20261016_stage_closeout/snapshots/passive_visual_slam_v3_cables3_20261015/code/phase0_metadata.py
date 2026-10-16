"""Read only bounded ZIP metadata from official ETH3D hosts; never a full GET."""
import concurrent.futures, datetime, hashlib, json, os, pathlib, re, shutil, struct, time, zipfile, requests
ROOT=pathlib.Path('/home/wcqw/passive_visual_slam_v3_cables3_20261015')
DATA=pathlib.Path('/media/wcqw/KESU/slam_research/v3_cables3_20261015')
HEADERS={'User-Agent':'SLAM-academic-data-qualification/1.0','Accept-Encoding':'identity'}
HOSTS=['https://www.eth3d.net','https://eth3d.net','https://eth3d.ethz.ch']
def request_range(url,byte_range,cap):
    start=time.monotonic()
    with requests.get(url,headers={**HEADERS,'Range':byte_range},stream=True,timeout=(5,10)) as r:
        meta=dict(url=url,final_url=r.url,status=r.status_code,headers=dict(r.headers),requested_range=byte_range)
        if r.status_code!=206:
            return meta,None
        data=b''
        for b in r.iter_content(16384):
            data+=b
            if len(data)>cap:raise RuntimeError('metadata byte cap exceeded')
            if time.monotonic()-start>20:raise TimeoutError('metadata total time cap')
        return meta,data
def inspect(mode):
    events=[]
    for host in HOSTS:
        url=host+'/data/slam/datasets/cables_3_'+mode+'.zip'
        t=time.monotonic();e={'url':url,'mode':mode,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            meta,tail=request_range(url,'bytes=-65536',65536);e.update(meta)
            if tail is None:raise RuntimeError('official server did not return bounded Range metadata')
            total=int(re.fullmatch(r'bytes \d+-\d+/(\d+)',meta['headers']['Content-Range']).group(1))
            (ROOT/'audit'/('zip_tail_'+mode+'.bin')).write_bytes(tail)
            pos=tail.rfind(b'PK\x05\x06')
            if pos<0:raise RuntimeError('EOCD not in bounded tail')
            _,disk,cd_disk,n_disk,n_total,cd_size,cd_offset,comment=struct.unpack_from('<4s4H2LH',tail,pos)
            if disk or cd_disk or n_disk!=n_total or cd_size==0xffffffff:raise RuntimeError('multidisk/ZIP64 not supported in this bounded probe')
            if cd_size>524288:raise RuntimeError('central directory metadata cap exceeded')
            tail_offset=total-len(tail)
            if cd_offset>=tail_offset:cd=tail[cd_offset-tail_offset:cd_offset-tail_offset+cd_size]
            else:
                cm,cd=request_range(url,f'bytes={cd_offset}-{cd_offset+cd_size-1}',524288)
                e['central_directory_request']=cm
                if cd is None:raise RuntimeError('central directory Range unavailable')
            entries=[];off=0
            while off<len(cd):
                v=struct.unpack_from('<4s6H3L5H2L',cd,off)
                if v[0]!=b'PK\x01\x02':raise RuntimeError('central directory signature mismatch')
                name=cd[off+46:off+46+v[10]].decode('utf-8' if v[3]&2048 else 'cp437')
                entries.append(dict(name=name,compressed=v[8],uncompressed=v[9],crc32=v[7]))
                off+=46+v[10]+v[11]+v[12]
            if len(entries)!=n_total:raise RuntimeError('entry count mismatch')
            result=dict(mode=mode,url=url,compressed_bytes=total,uncompressed_bytes=sum(x['uncompressed'] for x in entries),entries=entries)
            (ROOT/'audit'/('zip_metadata_'+mode+'.json')).write_text(json.dumps(result,indent=2))
            e['qualified_metadata']=True;e['seconds']=time.monotonic()-t;events.append(e)
            return result,events
        except Exception as ex:e['error']=str(ex)
        e['seconds']=time.monotonic()-t;events.append(e)
    return None,events
if __name__=='__main__':
    # Tiny fresh-file write check; retains its content and never alters old files.
    with (DATA/'write_qualification.txt').open('x') as f:f.write('V3 new workspace writable; no historical data altered.\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(inspect,['mono','rgbd']))
    (ROOT/'audit/metadata_requests.json').write_text(json.dumps([e for r,ee in results for e in ee],indent=2))
    valid=all(r is not None for r,e in results)
    summary=dict(metadata_qualified=valid,root_free=shutil.disk_usage('/').free,data_free=shutil.disk_usage(DATA).free,data_directory=str(DATA),system_reserve=1073741824,body_scope='ZIP metadata only',scientific_runs=0)
    if valid:
        summary['archive_bytes']=sum(r['compressed_bytes'] for r,e in results)
        summary['uncompressed_upper_bound']=sum(r['uncompressed_bytes'] for r,e in results)
        summary['peak_data_upper_bound']=summary['archive_bytes']+summary['uncompressed_upper_bound']+200*1024*1024
        summary['space_qualified']=summary['root_free']>summary['system_reserve'] and summary['peak_data_upper_bound']+summary['system_reserve']<=summary['data_free']
    (ROOT/'audit/phase0_metadata_result.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
