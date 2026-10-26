"""Only newly created synthetic directories are touched by these tests."""
from pathlib import Path
import ast
import os
import sys
import time

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench.native_scratch import OwnedScratch, ScratchRefused


def test_nested_opaque_contents_removed_and_capability_consumed(tmp_path):
    scratch=OwnedScratch(tmp_path/'owned')
    (scratch.path/'nested').mkdir()
    (scratch.path/'nested'/'opaque').write_bytes(b'synthetic opaque output')
    assert scratch.cleanup(time.monotonic()+2,writers_closed=True) is True
    assert scratch.removed is True and not scratch.path.exists()
    with pytest.raises(ScratchRefused):scratch.cleanup(time.monotonic()+2,writers_closed=True)


def test_existing_directory_is_never_adopted(tmp_path):
    path=tmp_path/'existing';path.mkdir();(path/'keep').write_text('synthetic')
    with pytest.raises(FileExistsError):OwnedScratch(path)
    assert (path/'keep').read_text()=='synthetic'


def test_symlink_is_refused_without_following_it(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_text('synthetic')
    scratch=OwnedScratch(tmp_path/'owned');(scratch.path/'link').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ScratchRefused,match='symlink'):scratch.cleanup(time.monotonic()+2,writers_closed=True)
    assert (outside/'keep').read_text()=='synthetic'
    assert (scratch.path/'link').is_symlink() and scratch.removed is False


@pytest.mark.parametrize('where',['root','parent'])
def test_replacement_identity_never_deleted(tmp_path,where):
    parent=tmp_path/'parent';parent.mkdir();scratch=OwnedScratch(parent/'owned')
    target=scratch.path if where=='root' else parent
    target.rename(tmp_path/'moved');target.mkdir()
    (target/'keep').write_text('synthetic')
    with pytest.raises((ScratchRefused,FileNotFoundError)):
        scratch.cleanup(time.monotonic()+2,writers_closed=True)
    assert (target/'keep').read_text()=='synthetic' and scratch.removed is False


@pytest.mark.parametrize('writers',[False,None,1,'yes'])
def test_no_cleanup_until_exact_writers_are_gone(tmp_path,writers):
    scratch=OwnedScratch(tmp_path/'owned');(scratch.path/'keep').write_text('synthetic')
    with pytest.raises(ScratchRefused):scratch.cleanup(time.monotonic()+2,writers_closed=writers)
    assert (scratch.path/'keep').read_text()=='synthetic' and scratch.removed is False


@pytest.mark.parametrize('kind',['entries','depth','deadline'])
def test_original_cleanup_budget_is_not_reset(tmp_path,kind):
    scratch=OwnedScratch(tmp_path/'owned');(scratch.path/'child').mkdir()
    (scratch.path/'child'/'keep').write_text('synthetic')
    options={'max_entries':0} if kind=='entries' else {'max_depth':0} if kind=='depth' else {}
    with pytest.raises((ScratchRefused,TimeoutError)):
        scratch.cleanup(time.monotonic()+(-1 if kind=='deadline' else 2),writers_closed=True,**options)
    assert scratch.removed is False
    with pytest.raises(ScratchRefused):scratch.cleanup(time.monotonic()+2,writers_closed=True)


def test_deadline_is_rechecked_during_traversal(tmp_path):
    scratch=OwnedScratch(tmp_path/'owned');(scratch.path/'keep').write_text('synthetic')
    calls=[]
    def now():
        calls.append(1)
        return 0 if len(calls)<4 else 10
    with pytest.raises(TimeoutError):scratch.cleanup(5,writers_closed=True,now=now)
    assert scratch.removed is False


@pytest.mark.parametrize('deadline',[None,False,float('nan'),float('inf')])
def test_invalid_deadline_does_not_start_cleanup(tmp_path,deadline):
    scratch=OwnedScratch(tmp_path/'owned');(scratch.path/'keep').write_text('synthetic')
    with pytest.raises(ScratchRefused):scratch.cleanup(deadline,writers_closed=True)
    assert (scratch.path/'keep').exists()


def test_cleanup_never_reads_contents_or_retains_names():
    path=Path(__file__).resolve().parents[1]/'src/workbench/native_scratch.py'
    tree=ast.parse(path.read_text())
    assert not any(isinstance(n,ast.Attribute) and n.attr in {'read','read_text','read_bytes','write_text','write_bytes'} for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print' for n in ast.walk(tree))
