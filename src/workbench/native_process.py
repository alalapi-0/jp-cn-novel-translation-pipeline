"""Owned Linux sessions and bounded JSON RPC; no shared-process controls."""
from __future__ import annotations
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import threading
import time


class NativeCancelled(RuntimeError):
    pass


# Only trusted local branches create these finite public facts. Backend error
# codes and messages never become exception arguments or attributes.
NATIVE_FAILURE_REASONS = frozenset({
    'unknown', 'rpc_rejected', 'unexpected_tool_or_approval_request',
    'metadata_output_limit', 'stdout_limit', 'stderr_limit',
    'process_exited_before_response', 'admission_changed',
    'unexpected_tool_event', 'thread_event_mismatch', 'turn_event_mismatch',
    'turn_not_completed', 'turn_error', 'answer_missing_or_too_large', 'turn_start_unverified',
    'receipt_output_limit', 'receipt_serialization_failed',
    'schema_validation_failed',
})


class NativeFailure(RuntimeError):
    def __init__(self, reason_code):
        reason = reason_code if type(reason_code) is str and reason_code in NATIVE_FAILURE_REASONS else 'unknown'
        super().__init__('native_failure:' + reason)
        self.reason_code = reason


def identity(pid):
    try:
        parts=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
        return {'pid':pid,'state':parts[0],'pgid':int(parts[2]),'sid':int(parts[3]),'start_ticks':int(parts[19])}
    except (FileNotFoundError,ProcessLookupError):return None


class OwnedProcess:
    """A new session per fixed native child, with bounded reads and cancellation."""
    def __init__(self,command,*,cwd,env,cancel=None):
        self.cancel=cancel or threading.Event()
        self.process=subprocess.Popen(command,cwd=cwd,env=env,start_new_session=True,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
        self.pid=self.process.pid;self.initial=identity(self.pid)
        if self.initial and (self.initial['pgid']!=self.pid or self.initial['sid']!=self.pid):
            self.process.kill();self.process.wait();raise RuntimeError('native_session_not_owned')
        self.selector=selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ,'stdout')
        self.selector.register(self.process.stderr,selectors.EVENT_READ,'stderr')
        self.out=bytearray();self.err=bytearray();self.total=0;self.closed=False;self.cleanup_verified=False
        os.set_blocking(self.process.stdin.fileno(),False)

    def _check(self,deadline):
        if self.cancel.is_set():raise NativeCancelled('native_operation_cancelled')
        if time.monotonic()>=deadline:raise TimeoutError('native_deadline_exceeded')

    def send(self,value,deadline):
        data=value if isinstance(value,bytes) else (json.dumps(value)+'\n').encode()
        view=memoryview(data)
        while view:
            self._check(deadline)
            try:n=os.write(self.process.stdin.fileno(),view);view=view[n:]
            except BlockingIOError:time.sleep(.01)

    def pump(self,deadline):
        self._check(deadline)
        for key,_ in self.selector.select(timeout=min(.1,max(.001,deadline-time.monotonic()))):
            chunk=os.read(key.fileobj.fileno(),65536)
            if not chunk:self.selector.unregister(key.fileobj);continue
            if key.data=='stderr':
                self.err.extend(chunk)
                if len(self.err)>65536:raise NativeFailure('stderr_limit')
            else:
                self.total+=len(chunk)
                if self.total>8*1024*1024:raise NativeFailure('stdout_limit')
                self.out.extend(chunk)

    def line(self,deadline):
        while b'\n' not in self.out:
            self.pump(deadline)
            if self.process.poll() is not None and not self.selector.get_map() and b'\n' not in self.out:
                raise NativeFailure('process_exited_before_response')
        line,_,rest=self.out.partition(b'\n');self.out=bytearray(rest)
        return json.loads(line)

    def communicate(self,data=b'',timeout=10):
        deadline=time.monotonic()+timeout
        try:
            if data:self.send(data,deadline)
            self.process.stdin.close()
            while self.selector.get_map():self.pump(deadline)
            self.process.wait(timeout=max(.01,deadline-time.monotonic()))
            return bytes(self.out),bytes(self.err)
        finally:self.close()

    def members(self):
        current=identity(self.pid)
        if current and self.initial and current['start_ticks']!=self.initial['start_ticks']:
            raise RuntimeError('native_pid_identity_changed; no signal sent')
        result=[]
        for path in Path('/proc').iterdir():
            if path.name.isdigit():
                item=identity(int(path.name))
                if item and item['sid']==self.pid and item['state']!='Z':result.append(item)
        return result

    def close(self):
        if self.closed:return
        try:
            for sig,seconds in [(signal.SIGTERM,1),(signal.SIGKILL,1)]:
                for group in {item['pgid'] for item in self.members()}:
                    try:os.killpg(group,sig)
                    except ProcessLookupError:pass
                deadline=time.monotonic()+seconds
                while self.members() and time.monotonic()<deadline:time.sleep(.01)
                if not self.members():break
            self.process.wait(timeout=2)
            if self.members():raise RuntimeError('native_owned_descendants_still_running')
            self.cleanup_verified=True
        finally:
            self.closed=True;self.selector.close()
            for stream in [self.process.stdin,self.process.stdout,self.process.stderr]:
                if not stream.closed:stream.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class NativeRPC:
    def __init__(self,owned,timeout=30):
        self.owned=owned;self.deadline=time.monotonic()+timeout;self.seq=0;self.notifications=[]

    def receive(self):
        value=self.owned.line(self.deadline)
        if 'id' in value and 'method' in value:
            raise NativeFailure('unexpected_tool_or_approval_request')
        return value

    def call(self,method,params):
        self.seq+=1;seq=self.seq
        self.owned.send({'id':seq,'method':method,'params':params},self.deadline)
        while True:
            value=self.receive()
            if value.get('id')==seq:
                if 'error' in value:raise NativeFailure('rpc_rejected')
                return value['result']
            self.notifications.append(value)

    def notify(self,method):self.owned.send({'method':method},self.deadline)
