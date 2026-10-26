"""Immutable export snapshots with one atomic, locally locked current pointer.

Aliases always traverse that pointer. Legacy regular files are copied verbatim
before alias conversion; no cleanup or original-data deletion is performed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from providers.controlled_run import checkpoint_lock
from .source_versions import value_sha


def _safe(root, relative):
    relative=Path(relative)
    if relative.is_absolute() or not relative.parts or any(p in {'.','..'} for p in relative.parts):
        raise ValueError('ordinary relative export path required')
    path=root/relative
    for parent in [root,*list(path.parents)[:len(relative.parts)-1]]:
        if parent.is_symlink(): raise ValueError('export parent symlink is unmanaged')
    return path


def _state(path):
    if path.is_symlink(): return ('link',os.readlink(path))
    if not path.exists(): return None
    if not path.is_file(): raise ValueError('export alias must be an ordinary file or managed link')
    return ('file',hashlib.sha256(path.read_bytes()).hexdigest())


def _sync(directory):
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _link(path,target):
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        os.symlink(target,temporary)
        os.replace(temporary,path)
        _sync(path.parent)
    finally:
        if temporary.is_symlink(): temporary.unlink()


def _snapshot(root,files):
    store=_safe(root,'.revisions')
    if store.is_symlink(): raise ValueError('export snapshot store symlink is unmanaged')
    store.mkdir(exist_ok=True)
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}
    revision=value_sha(hashes);target=store/revision
    if target.exists():
        _verify(root,revision)
        return revision
    stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=store))
    try:
        for name,raw in files.items():
            if Path(name).name!=name or name in {'.','..'} or not isinstance(raw,bytes):
                raise ValueError('bundle members require flat names and bytes')
            with (stage/name).open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            (stage/name).chmod(0o444)
        _sync(stage);os.rename(stage,target);_sync(store)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    _verify(root,revision)
    return revision


def _verify(root,revision):
    if not re.fullmatch('[0-9a-f]{64}',revision): raise ValueError('invalid export snapshot identity')
    path=_safe(root,Path('.revisions')/revision)
    if path.is_symlink() or not path.is_dir(): raise ValueError('missing export snapshot')
    hashes={}
    for member in path.iterdir():
        if member.is_symlink() or not member.is_file(): raise ValueError('unmanaged snapshot member')
        hashes[member.name]=hashlib.sha256(member.read_bytes()).hexdigest()
    if not hashes or value_sha(hashes)!=revision: raise ValueError('export snapshot content changed')
    return {'revision':revision,'path':path,'files_sha256':hashes}


def read_current(root,*,pointer='.current'):
    root=Path(root);path=_safe(root,pointer)
    if not path.exists() and not path.is_symlink(): return None
    if not path.is_symlink(): raise ValueError('unmanaged export pointer')
    target=os.readlink(path)
    if not re.fullmatch(r'\.revisions/[0-9a-f]{64}',target): raise ValueError('foreign export pointer')
    return _verify(root,target.split('/')[-1])


def publish_bundle(root,files,aliases,*,pointer='.current',before_commit=None):
    root=Path(root)
    if root.is_symlink(): raise ValueError('export root symlink is unmanaged')
    # Check every existing ancestor before allocating anything.
    if any(p.is_symlink() for p in root.parents): raise ValueError('export ancestor symlink is unmanaged')
    if not files or not aliases or any(member not in files for member in aliases.values()):
        raise ValueError('complete export bundle and aliases required')
    if Path(pointer).name!=pointer or pointer in {'.','..'}: raise ValueError('flat pointer name required')
    root.mkdir(parents=True,exist_ok=True)
    with checkpoint_lock(root/'export-transaction'):
        current=read_current(root,pointer=pointer)
        destinations={relative:_safe(root,relative) for relative in aliases}
        prior={name:_state(path) for name,path in destinations.items()}
        links={name:os.path.relpath(root/pointer/member,destinations[name].parent) for name,member in aliases.items()}
        for name,state in prior.items():
            if state and state[0]=='link' and state[1]!=links[name]: raise ValueError('foreign export alias preserved')
        if current is None and any(prior.values()) and not all(prior.values()):
            raise ValueError('incomplete legacy export preserved')
        revision=_snapshot(root,files)
        # Detect owner edits while staging, including same-size changes.
        if any(_state(path)!=prior[name] for name,path in destinations.items()):
            raise RuntimeError('export preimage changed while staging')
        observed=read_current(root,pointer=pointer)
        if (observed or {}).get('revision')!=(current or {}).get('revision'):
            raise RuntimeError('export pointer changed while staging')
        if current is None and all(prior.values()):
            if any(state[0]!='file' for state in prior.values()): raise ValueError('unmanaged legacy aliases')
            legacy={aliases[name]:path.read_bytes() for name,path in destinations.items()}
            old=_snapshot(root,legacy)
            if any(_state(path)!=prior[name] for name,path in destinations.items()):
                raise RuntimeError('legacy export changed before alias conversion')
            _link(root/pointer,'.revisions/'+old);current=read_current(root,pointer=pointer)
        created=[]
        try:
            for name,path in destinations.items():
                path.parent.mkdir(parents=True,exist_ok=True)
                if _state(path)!=prior[name]: raise RuntimeError('export alias preimage changed')
                if prior[name] and prior[name][0]=='file' and current is not None:
                    if path.read_bytes()!=(current['path']/aliases[name]).read_bytes():
                        raise ValueError('legacy alias differs from current snapshot')
                if prior[name] is None: created.append(name)
                _link(path,links[name])
            if before_commit is not None: before_commit()
            if any(_state(path)!=('link',links[name]) for name,path in destinations.items()):
                raise RuntimeError('export alias changed before commit')
            observed=read_current(root,pointer=pointer)
            if (observed or {}).get('revision')!=(current or {}).get('revision'):
                raise RuntimeError('export pointer changed before commit')
            try: _link(root/pointer,'.revisions/'+revision)
            except BaseException:
                # A replace may have committed before its observer failed.
                if (read_current(root,pointer=pointer) or {}).get('revision')!=revision: raise
            final=read_current(root,pointer=pointer)
            if final['revision']!=revision: raise RuntimeError('export commit identity not observed')
            return {'bundle_revision':revision,'snapshot_path':str(final['path']),
                    'pointer':str(root/pointer),'files_sha256':final['files_sha256']}
        except BaseException:
            observed=read_current(root,pointer=pointer)
            if observed is None:
                for name in created:
                    if _state(destinations[name])==('link',links[name]): destinations[name].unlink()
            raise
