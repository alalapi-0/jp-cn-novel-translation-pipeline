#!/usr/bin/env python3
"""Explicit local CLI for shared Workbench services; native jobs require consent."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workbench.canonical_service import (selection_status, restore_previous_candidates,
    import_sources, select_revision, export_selected)


def public_result(result):
    """Finite terminal receipt: source/target/reviewer bodies and native IDs stay local."""
    keys={'action','project_id','request_id','input_manifest_sha256','segments_created',
        'segments_exported','chapters_exported','changed_segment_ids','approval_issued',
        'canonical_adoption','human_approved_final','bundle_revision','idempotent_replay'}
    value={k:v for k,v in result.items() if k in keys}
    if 'selection' in result:
        value['selection']={k:v for k,v in result['selection'].items() if k!='segments'}
    if 'accepted_revision' in result:
        value['accepted_revision_sha256']=result['accepted_revision'].get('revision_sha256')
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description='显式导入、Agent 额度生成/审查、恢复、选择和安全导出。')
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--project',required=True)
    commands=parser.add_subparsers(dest='action',required=True)
    commands.add_parser('status')
    restore=commands.add_parser('restore-previous')
    restore.add_argument('--expected-manifest-sha256',required=True)
    restore.add_argument('--confirm-restore',action='store_true',required=True)
    source=commands.add_parser('source-import')
    source.add_argument('--direction',choices=['JP_TO_CN','CN_TO_JP'],required=True)
    source.add_argument('--source-file',type=Path,nargs='+',required=True)
    source.add_argument('--name')
    for name in ['native-job','select-version','export-selected']:
        command=commands.add_parser(name)
        command.add_argument('--expected-manifest-sha256',required=True)
        if name=='native-job':
            command.add_argument('--action',dest='action_native',choices=['generate','review'],required=True)
            command.add_argument('--request-id',required=True)
            command.add_argument('--confirm-native',action='store_true',required=True)
        elif name=='select-version':command.add_argument('--confirm-select',action='store_true',required=True)
        else:command.add_argument('--confirm-replace',action='store_true',required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='status':result={'selection':selection_status(args.root,args.project)}
        elif args.action=='source-import':
            chapters=[]
            for path in args.source_file:
                if path.is_symlink() or any(p.is_symlink() for p in path.absolute().parents) or not path.is_file() or path.stat().st_size>8*1024*1024:
                    raise ValueError('ordinary bounded source files required')
                chapters.append({'filename':path.name,'text':path.read_bytes().decode('utf-8')})
            result={'selection':import_sources(args.root,project_id=args.project,name=args.name,
                language_direction=args.direction,chapters=chapters)}
        elif args.action=='restore-previous':result=restore_previous_candidates(args.root,args.project,expected_manifest_sha256=args.expected_manifest_sha256)
        elif args.action=='native-job':
            from workbench.native_agent import execute_job
            result=execute_job(args.root,args.project,expected_manifest_sha256=args.expected_manifest_sha256,
                request_id=args.request_id,action=args.action_native)
        elif args.action=='select-version':
            state=selection_status(args.root,args.project)
            result={'selection':select_revision(args.root,args.project,expected_manifest_sha256=args.expected_manifest_sha256,
                target_fields={r['segment_id']:'draft' for r in state['segments']})}
        else:
            result=export_selected(args.root,args.project,expected_manifest_sha256=args.expected_manifest_sha256)
            result['selection']=selection_status(args.root,args.project)
        print(json.dumps(public_result(result),ensure_ascii=False,sort_keys=True));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
        print(json.dumps({'error_type':type(exc).__name__,'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
