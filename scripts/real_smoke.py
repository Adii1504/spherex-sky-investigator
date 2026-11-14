"""Opt-in integration check against public IRSA, never part of offline tests."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from whylab.app import create_app
from whylab.config import Settings
from whylab.integration import build_adapters
from whylab.security import TrustedRetriever

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ra',type=float,default=127.69444)
    parser.add_argument('--dec',type=float,default=-39.17760)
    parser.add_argument('--fov',type=float,default=2)
    args=parser.parse_args()
    settings=Settings(max_observations=36,timeout_seconds=180)
    archive,science,motion=build_adapters(settings,TrustedRetriever(settings.trusted_hosts,60))
    sky={'ra_deg':args.ra,'dec_deg':args.dec,'fov_arcmin':args.fov}
    with TestClient(create_app(settings,archive,science,motion)) as client:
        response=client.post('/api/v1/observations/search',json=sky)
        response.raise_for_status();search=response.json()
        selected=[];exposures=set()
        for o in search['observations']:
            if o['detector']=='1' and o['exposure_id'] not in exposures:
                selected.append(o['id']);exposures.add(o['exposure_id'])
            if len(selected)==4:break
        if not selected:raise RuntimeError('No detector-1 observations in this field; try another sky position')
        selection={**sky,'search_id':search['search_id'],'observation_ids':selected}
        response=client.post('/api/v1/sequences',json=selection);response.raise_for_status();job=response.json()['job_id']
        def wait(key):
            for _ in range(240):
                record=client.get('/api/v1/jobs/'+key).json()
                if record['status']=='failed':raise RuntimeError(record['error'])
                if record['status']=='succeeded':return record['result']
                time.sleep(1)
            raise RuntimeError('Integration check timed out')
        result=wait(job)
        for i,p in enumerate(result['previews']):
            image=client.get(p['preview_url']);image.raise_for_status()
            assert image.content.startswith(b'\x89PNG')
            Path(f'.data/real-frame-{i+1}.png').write_bytes(image.content)
        response=client.post('/api/v1/investigations',json={**selection,'sequence_job_id':job});response.raise_for_status();key=response.json()['investigation_id']
        verification=None
        if len(selected)>=2:
            response=client.post(f'/api/v1/investigations/{key}/verify',json={'training_observation_ids':selected[:-1],'reserved_observation_ids':selected[-1:]})
            response.raise_for_status();verification=wait(response.json()['job_id'])
        evidence=client.get(f'/api/v1/investigations/{key}/evidence');evidence.raise_for_status()
        Path('.data/real-evidence.json').write_text(json.dumps(evidence.json(),indent=2),encoding='utf-8')
        print(json.dumps({'observations':len(search['observations']),'selected_exposures':len(selected),'previews':len(result['previews']),'processing_version':result['processing_version'],'verification_outcome':verification['outcome'] if verification else 'not run','warnings':result['warnings']},indent=2))

if __name__=='__main__':main()
