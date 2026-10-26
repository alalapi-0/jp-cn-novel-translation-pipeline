"""Real disposable child sessions; no Codex/model/network processes are started."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench.native_process import OwnedProcess,NativeCancelled,NativeRPC,identity


@pytest.mark.parametrize('cause',['timeout','cancel','parent_exit'])
def test_owned_session_cleans_descendants_and_preserves_unrelated_child(tmp_path,cause):
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
    event=threading.Event()
    code="import os,time;child=os.fork();os.setpgrp() if not child else None;print(child if child else os.getpid(),flush=True);time.sleep(30)"
    if cause=='parent_exit':code="import os,time;child=os.fork();os.setpgrp() if not child else None;print(child if child else os.getpid(),flush=True);os._exit(0) if child else time.sleep(30)"
    owned=OwnedProcess([sys.executable,'-c',code],cwd=tmp_path,env={'PATH':os.environ['PATH']},cancel=event)
    try:
        # Read an actual child identity before provoking cleanup.
        while b'\n' not in owned.out:owned.pump(time.monotonic()+3)
        child=int(owned.out.splitlines()[0]);assert child>0
        if cause=='cancel':event.set()
        with pytest.raises((NativeCancelled,TimeoutError)):
            owned.communicate(timeout=.15)
        assert owned.closed and owned.cleanup_verified and not owned.members()
        actual=identity(child);assert actual is None or actual['state']=='Z'
        assert unrelated.poll() is None
    finally:
        owned.close();unrelated.terminate();unrelated.wait(timeout=3)


def test_rpc_rejects_tool_or_approval_requests_before_reply(tmp_path):
    code='import json;print(json.dumps({"id":42,"method":"item/commandExecution/requestApproval"}),flush=True)'
    with OwnedProcess([sys.executable,'-c',code],cwd=tmp_path,env={'PATH':os.environ['PATH']}) as owned:
        with pytest.raises(RuntimeError,match='native_failure:unexpected_tool_or_approval_request'):
            NativeRPC(owned).receive()


@pytest.mark.parametrize('code',[12345,None,False,'SYNTHETIC_PRIVATE',{'nested':'SYNTHETIC_PRIVATE'},['SYNTHETIC_PRIVATE']])
def test_r40_rpc_backend_codes_never_escape(code):
    class FakeOwned:
        def send(self,*a):pass
        def line(self,*a):return {'id':1,'error':{'code':code,'message':'SYNTHETIC_PRIVATE'}}
    with pytest.raises(RuntimeError) as failed:NativeRPC(FakeOwned()).call('synthetic',{})
    assert str(failed.value)=='native_failure:rpc_rejected'
    assert failed.value.reason_code=='rpc_rejected'
    assert 'SYNTHETIC_PRIVATE' not in repr(vars(failed.value))
