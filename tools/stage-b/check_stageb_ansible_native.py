"""Native Ansible orchestration with local mock agents. No real SSH/nft/kubectl."""
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile, yaml

base = Path(tempfile.mkdtemp(prefix='p1lb_ansible_mock_'))
print('LOCAL_MOCK_OUTPUT=' + str(base), flush=True)
source = Path(__file__).resolve().parent / 'ansible'
env = dict(os.environ, ANSIBLE_NOCOLOR='1')
if os.environ.get('ANSIBLE_TEST_PYTHONPATH'):
 env['PYTHONPATH'] = os.environ['ANSIBLE_TEST_PYTHONPATH']
mock = r'''
import argparse,json,pathlib,time,tarfile
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--role');p.add_argument('--inputs');p.add_argument('--sequence');a=p.parse_args()
d=json.loads(pathlib.Path(a.inputs).read_text());f=pathlib.Path(d['home']);f.mkdir(exist_ok=True)
def save(s):
 t=f/'state.tmp';t.write_text(json.dumps(s));t.replace(f/'state.json')
def read():return json.loads((f/'state.json').read_text()) if (f/'state.json').exists() else {'status':'PREPARED'}
if a.action=='observe':
 save({'status':'OBSERVING','sequence':1,'age_seconds':0,'run_id':d['run_id'],'sample':{'success':True}})
 end=time.monotonic()+60
 while not (f/'stop').exists() and time.monotonic()<end:time.sleep(.1)
elif a.action=='inject':
 save({'status':'BASELINE'})
 end=time.monotonic()+60
 while read()['status'] not in ['PASS_CANDIDATE','STOP'] and time.monotonic()<end:time.sleep(.1)
elif a.action=='status':
 s=read()
 if a.role=='cp' and s['status']=='OBSERVING':
  s['sequence']+=1
  if d['case']=='api_failure' and s['sequence']>=4:s['status']='STOP'
  save(s)
 if a.role=='lb' and s['status']=='BASELINE':
  n=int((f/'polls').read_text())+1 if (f/'polls').exists() else 1
  (f/'polls').write_text(str(n))
  if n>=3:save({'status':'PASS_CANDIDATE'})
 print(json.dumps(read()))
elif a.action=='abort':
 (f/'abort_received').write_text('yes');save({'status':'STOP'})
elif a.action=='stop':(f/'stop').write_text('yes')
elif a.action=='lease':
 n=int(a.sequence);prev=int((f/'lease').read_text()) if (f/'lease').exists() else 0
 assert n>prev
 (f/'lease').write_text(str(n))
elif a.action=='archive':
 out=f/('P1_LB_STAGEB_'+d['run_id']+'.tar.gz')
 with tarfile.open(out,'w:gz') as t:t.add(f/'state.json',arcname='MOCK_ONLY.json')
 pathlib.Path(str(out)+'.sha256').write_text('MOCK_ONLY')
 print('{}')
'''
(base/'mock_agent.py').write_text(mock)
outcomes=[]
for case in ['success','api_failure']:
 folder=base/case;folder.mkdir(exist_ok=True)
 evidence=folder/'evidence';evidence.mkdir(exist_ok=True)
 for n in ['poll.yml','fetch.yml']:shutil.copyfile(source/n,folder/n)
 play=yaml.safe_load((source/'runtime.yml').read_text())[1:]
 (folder/'play.yml').write_text(yaml.safe_dump(play,sort_keys=False))
 inventory={'all':{'hosts':{}}}
 for role,host in [('cp','k8s-control01'),('lb','k8s-api-lb01')]:
  home=folder/role;home.mkdir(exist_ok=True)
  inp=folder/(role+'.json');inp.write_text(json.dumps({'home':str(home),'run_id':'a'*32,'case':case}))
  inventory['all']['hosts'][host]={'ansible_connection':'local','ansible_python_interpreter':sys.executable,
   'role':role,'login':{'home':str(home)},'agent':[sys.executable,str(base/'mock_agent.py')],
   'agent_args':['--role',role,'--inputs',str(inp)]}
 (folder/'inventory.yml').write_text(yaml.safe_dump(inventory))
 command=[sys.executable,'-m','ansible.cli.playbook','-i',str(folder/'inventory.yml'),str(folder/'play.yml'),
          '-e',json.dumps({'inputs':{'run_id':'a'*32},'evidence_dir':str(evidence)})]
 proc=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
 (folder/'ansible.log').write_text(proc.stdout)
 if (proc.returncode==0)!=(case=='success'):
  print(proc.stdout);raise AssertionError((case,proc.returncode))
 state=json.loads((evidence/'COORDINATION.json').read_text())
 assert state['orchestration_error']==(case=='api_failure'),state
 assert (folder/'lb/abort_received').exists()==(case=='api_failure')
 assert all((evidence/(role+'.tar.gz')).is_file() for role in ['cp','lb'])
 outcomes.append({'case':case,'rc':proc.returncode,'result':'PASS'})
 print(outcomes[-1],flush=True)

# Unmodified production identity gates must reject local container before staging.
folder=base/'guard';folder.mkdir(exist_ok=True)
inventory={'all':{'hosts':{h:{'ansible_connection':'local','ansible_python_interpreter':sys.executable,
 'ansible_host':ip,'ansible_user':u} for h,ip,u in [('k8s-control01','10.1.93.102','svc_ansible'),('k8s-api-lb01','10.1.93.109','server01_k8s-api-lb')]}}}
(folder/'inventory.yml').write_text(yaml.safe_dump(inventory))
proc=subprocess.run([sys.executable,'-m','ansible.cli.playbook','-i',str(folder/'inventory.yml'),str(source/'runtime.yml'),
 '--tags','access','-e',json.dumps({'inputs':{'lb_user':'server01_k8s-api-lb'}})],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
(folder/'ansible.log').write_text(proc.stdout)
assert proc.returncode!=0 and 'Reject identity mismatch before creating any runtime folder' in proc.stdout
assert 'Stage into a new private work directory' not in proc.stdout
outcomes.append({'case':'unchanged_wrong_host_access_guard','rc':proc.returncode,'result':'PASS'})
(base/'RESULTS.json').write_text(json.dumps(outcomes,indent=2)+'\n')
print(outcomes[-1],flush=True)
