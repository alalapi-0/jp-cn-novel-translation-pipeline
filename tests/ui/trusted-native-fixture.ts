import {execFileSync} from 'node:child_process';

export function trustedSyntheticAgentSetup(project:string, segmentIds?:string[]) {
  // Test fixture setup calls the existing native CAS. The HTTP UI cannot supply this actor.
  // This is not a model evaluation or a production acceptance route.
  execFileSync('/venv/bin/python',['-c',`
import sys,json
from pathlib import Path
sys.path.insert(0,'/work/src')
from workbench.project_registry import get_project_manifest,patch_project_review_state_cas
from workbench.review_state import DecisionActor,approval_identity
meta=json.loads(Path('/work/.ui-fixture-root.json').read_text());root=Path(meta['root'])
assert meta['synthetic_only'] and root.parent==Path('/work/.cache') and root.name.startswith('ui-fixture-')
manifest=get_project_manifest(root,sys.argv[1])
patch_project_review_state_cas(root,manifest.project_id,decision_actor=DecisionActor('agent','synthetic-browser-fixture'),segments={r['id']:{'status':'approved','expected_identity':approval_identity(project_id=manifest.project_id,language_direction=manifest.language_direction,segment=r)} for r in manifest.segments if not json.loads(sys.argv[2]) or r['id'] in json.loads(sys.argv[2])})
`,project,JSON.stringify(segmentIds || [])],{cwd:'/work',stdio:'pipe'});
}
