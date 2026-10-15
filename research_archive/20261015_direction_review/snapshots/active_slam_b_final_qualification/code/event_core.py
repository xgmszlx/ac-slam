"""ROS-free sequencing and single-writer primitives for deterministic tests."""
import json,threading,queue,time,hashlib
from collections import deque
class Journal:
 def __init__(self,path):self.file=open(path,'x');self.lock=threading.Lock()
 def emit(self,stamp,seq,event,**detail):
  with self.lock:
   self.file.write(json.dumps(dict(stamp_ns=stamp,seq=seq,event=event,wall=time.monotonic(),detail=detail))+'\n');self.file.flush()
 def close(self):
  with self.lock:self.file.close()
class Sequencer:
 def __init__(self,capacity=200):self.pending=deque();self.inflight=None;self.capacity=capacity;self.seen=set();self.completed=set()
 def enqueue(self,ns,seq,raw):
  if ns in self.seen:raise ValueError('duplicate stamp')
  if len(self.pending)>=self.capacity:raise OverflowError('bounded input queue full')
  self.seen.add(ns);self.pending.append((ns,seq,raw))
 def next(self,ready):
  if self.inflight is not None or not self.pending:return None
  item=self.pending[0]
  if not ready(item[0]):return None
  self.inflight=self.pending.popleft();return self.inflight
 def complete(self,ns):
  if self.inflight is None or self.inflight[0]!=ns:raise ValueError('terminal event identity mismatch')
  self.completed.add(ns);self.inflight=None
class SingleWriter:
 def __init__(self,write,capacity=20000):
  self.write=write;self.q=queue.Queue(capacity);self.closed=False;self.lock=threading.Lock();self.error=None
  self.thread=threading.Thread(target=self.run);self.thread.start()
 def put(self,item):
  with self.lock:
   if self.closed:raise RuntimeError('writer already sealed')
   self.q.put_nowait(item)
 def run(self):
  try:
   while True:
    item=self.q.get()
    if item is None:self.q.task_done();return
    self.write(item);self.q.task_done()
  except Exception as e:self.error=e
 def seal(self):
  with self.lock:self.closed=True
  self.q.put(None);self.thread.join(10)
  if self.thread.is_alive() or self.error:raise RuntimeError('writer did not drain safely: '+str(self.error))
