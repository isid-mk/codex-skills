"""Sandbox-only Salesforce data client. Credentials and passwords are never logged.

Import DataOnlyClient from a run-specific orchestrator after preflight. This helper
is a write guard, not an unattended importer or a substitute for user clarification.
"""
import hashlib,json,re,shutil,subprocess,urllib.request,urllib.parse,urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads((ROOT/'assets/manifest.json').read_text(encoding='utf-8'))
BUSINESS=set(MANIFEST['objects'])
VERSION=r'\d{2,3}\.0'
ID=r'[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?'
FORBIDDEN={'Profile','UserRole','PermissionSet','PermissionSetAssignment','PermissionSetGroup','Group','GroupMember','Organization','RecordType','BranchMaster__c','DepartmentMaster__c','LoanKindMaster__c','UsageMaster__c','SpecialProgramMaster__c','CapitalMaster__c','GeneralPurposeMaster__c'}
AUDIT={'OwnerId','CreatedById','CreatedDate','LastModifiedById','LastModifiedDate','SystemModstamp','IsDeleted'}
USER_FIELDS=set().union(*(r['values'].keys() for r in json.loads((ROOT/'assets/user-records.json').read_text(encoding='utf-8'))))

class WriteBlocked(RuntimeError):pass

class MutationPolicy:
    def __init__(self,config):
        self.config=config
        self.created={}
        self.stopped=False

    def ready(self):
        c=self.config
        expected=hashlib.sha256((ROOT/'assets/business-records.json').read_bytes()).hexdigest()
        if self.stopped:raise WriteBlocked('前の失敗または不明点で停止中。読戻しと疑問解消が必要です。')
        if c.get('preflight_complete') is not True or c.get('unresolved')!=[]:
            raise WriteBlocked('事前照合未完了、または未解決事項があります。')
        if c.get('bundle_sha256')!=expected:raise WriteBlocked('確定したbundleと実行基準のハッシュが異なります。')

    def entity(self,api,method,row):
        if api in FORBIDDEN or api.endswith('__mdt'):raise WriteBlocked('設定・対象外オブジェクトへの書込みは禁止: '+api)
        if api=='User':
            if self.config.get('users_requested') is not True:raise WriteBlocked('ユーザー作成の明示依頼がありません。')
            if method!='POST':raise WriteBlocked('Userモードは新規作成のみです。更新は許可されません。')
            if set(row)-{'attributes','Id'}-USER_FIELDS:raise WriteBlocked('ユーザーの承認済み項目を超える変更です。')
        elif api in BUSINESS or api=='ContentVersion':
            if self.config.get('data_write_requested') is not True:raise WriteBlocked('業務データ投入の明示依頼がありません。')
        else:raise WriteBlocked('書込み許可リスト外: '+api)
        if AUDIT & set(row):raise WriteBlocked('所有者・システム監査項目は送信できません。')
        if method=='POST' and row.get('Id'):raise WriteBlocked('新規作成へ環境依存IDを送信できません。')
        if method=='PATCH':
            sid=row.get('Id')
            allowed=set(self.created.get(api,[]))|set(self.config.get('authorized_update_ids',{}).get(api,[]))
            if sid not in allowed:raise WriteBlocked('既存重複レコードを更新しようとしています。')
            if sid not in self.created.get(api,[]):
                fields=set(self.config.get('authorized_update_fields',{}).get(api,{}).get(sid,[]))
                if set(row)-{'attributes','Id'}-fields:raise WriteBlocked('明示承認された更新項目を超えています。')
        def resolved(v):
            if isinstance(v,dict):return not any(k.startswith('$') for k in v) and all(resolved(x) for x in v.values())
            if isinstance(v,list):return all(resolved(x) for x in v)
            return True
        if not resolved(row):raise WriteBlocked('未解決の論理参照が残っています。')
        if api=='ContentVersion' and row.get('ContentDocumentId'):
            allowed=set(self.config.get('authorized_document_update_ids',[]))
            if row['ContentDocumentId'] not in allowed:raise WriteBlocked('未確認の既存文書へバージョンを追加できません。')

    def authorize(self,method,path,body=None):
        try:return self._authorize(method,path,body)
        except Exception:
            if method!='GET':self.stopped=True
            raise

    def _authorize(self,method,path,body=None):
        if method=='GET':
            if not re.match(r'^/services/data/v'+VERSION+r'/(?:query(?:/|\?)|tooling/query(?:/|\?)|sobjects/|ui-api/|limits(?:/|$))',path):
                raise WriteBlocked('許可された読み取りAPI以外です。')
            return []
        self.ready()
        if method not in ['POST','PATCH']:raise WriteBlocked('DELETE、PUT、その他の書込み操作は禁止です。')
        password=re.fullmatch(r'/services/data/v'+VERSION+r'/sobjects/User/('+ID+r')/password',path)
        if password:
            if method!='POST' or self.config.get('password_setting_requested') is not True:
                raise WriteBlocked('パスワード設定の明示依頼がありません。')
            if self.config.get('password_targets_verified') is not True or password[1] not in self.config.get('password_user_ids',[]):
                raise WriteBlocked('パスワード対象ユーザーが未確定、または対象外です。')
            if not isinstance(body,dict) or set(body)!={'NewPassword'} or not isinstance(body['NewPassword'],str) or not body['NewPassword']:
                raise WriteBlocked('パスワード設定本文が不正です。')
            return []
        if re.fullmatch(r'/services/data/v'+VERSION+r'/composite/sobjects',path):
            if not isinstance(body,dict) or set(body)!={'allOrNone','records'} or not isinstance(body['allOrNone'],bool):
                raise WriteBlocked('未許可のCompositeオプションです。')
            if not isinstance(body['records'],list) or not 1<=len(body['records'])<=200:raise WriteBlocked('Composite件数が不正です。')
            records=[]
            for r in body['records']:
                if not isinstance(r,dict) or set(r.get('attributes',{}))!={'type'}:raise WriteBlocked('Compositeの型指定が不正です。')
                api=r['attributes']['type'];self.entity(api,method,r);records.append((api,r))
            return records
        single=re.fullmatch(r'/services/data/v'+VERSION+r'/sobjects/([A-Za-z][A-Za-z0-9_]*)(?:/('+ID+r'))?',path)
        if not single or not isinstance(body,dict):raise WriteBlocked('設定API・Tooling書込み・匿名Apex等は禁止です。')
        api,sid=single.groups()
        if method=='PATCH' and not sid:raise WriteBlocked('更新対象IDがありません。')
        if method=='POST' and sid:raise WriteBlocked('新規作成URLが不正です。')
        row=dict(body)
        if sid:row['Id']=sid
        self.entity(api,method,row)
        return [(api,row)]

class DataOnlyClient:
    def __init__(self,config_path):
        self.config=json.loads(Path(config_path).read_text(encoding='utf-8'))
        c=self.config
        if not all(isinstance(c.get(k),str) and c[k] for k in ['target_alias','expected_org_id','expected_username']):
            raise WriteBlocked('投入先・組織ID・ログインユーザーが未確定です。')
        self.version=c.get('api_version','68.0')
        if not re.fullmatch(VERSION,self.version):raise WriteBlocked('APIバージョンが不正です。')
        self.policy=MutationPolicy(c);self.schemas={}
        cli=shutil.which('sf') or r'C:\Program Files\sf\bin\sf.cmd'
        auth=subprocess.run([cli,'org','display','--target-org',c['target_alias'],'--json'],capture_output=True,text=True,encoding='utf-8')
        try:parsed=json.loads(auth.stdout)
        except Exception:raise WriteBlocked('CLI認証の確認に失敗しました。') from None
        if auth.returncode or parsed.get('status'):raise WriteBlocked('対象環境への認証が必要です。')
        a=parsed['result']
        if a['id']!=c['expected_org_id'] or a['username']!=c['expected_username']:raise WriteBlocked('実際の認証先が指定と異なります。')
        self.url=a['instanceUrl'].rstrip('/');self.token=a['accessToken']
        if not re.fullmatch(r'https://[A-Za-z0-9-]+\.sandbox\.my\.salesforce\.com',self.url):raise WriteBlocked('Sandboxの接続URLではありません。')
        org=self.query('SELECT Id,IsSandbox FROM Organization')
        if len(org)!=1 or org[0]['Id']!=c['expected_org_id'] or org[0]['IsSandbox'] is not True:
            raise WriteBlocked('Sandbox組織の実照合に失敗しました。')
        name=c['expected_username'].replace('\\','\\\\').replace("'","\\'")
        actor=self.query("SELECT Id,Profile.Name FROM User WHERE Username='"+name+"'")
        if len(actor)!=1 or actor[0]['Profile']['Name'] not in ['システム管理者','System Administrator']:
            raise WriteBlocked('作成者がシステム管理者ではありません。所有者の方針確認が必要です。')
        self.actor_id=actor[0]['Id']

    def schema(self,api):
        if api not in self.schemas:self.schemas[api]=self.request('/services/data/v'+self.version+'/sobjects/'+api+'/describe')
        return self.schemas[api]

    def request(self,path,method='GET',body=None):
        entries=self.policy.authorize(method,path,body)
        try:
            for api,row in entries:
                schema=self.schema(api)
                if schema.get('customSetting') is True:raise WriteBlocked('Custom Settingsの書込みは禁止です。')
                fm={f['name']:f for f in schema['fields']}
                mode='createable' if method=='POST' else 'updateable'
                for k,v in row.items():
                    if k in ['attributes','Id']:continue
                    if k not in fm or not fm[k][mode] or fm[k]['calculated']:raise WriteBlocked('入力不可項目: '+api+'.'+k)
                    if isinstance(v,str) and fm[k].get('length') and len(v)>fm[k]['length']:raise WriteBlocked('桁数超過: '+api+'.'+k)
                    if fm[k]['type']=='reference' and v is not None and not re.fullmatch(ID,str(v)):raise WriteBlocked('参照IDが未解決: '+api+'.'+k)
        except Exception:
            if method!='GET':self.policy.stopped=True
            raise
        password=path.endswith('/password') and method=='POST'
        req=urllib.request.Request(self.url+path,data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},method=method)
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                data={} if response.status==204 else json.load(response)
                if password and response.status!=204:raise WriteBlocked('パスワード設定の成功応答を確認できません。')
        except Exception as e:
            if method!='GET':self.policy.stopped=True
            if password:raise WriteBlocked('パスワード設定失敗。値は出力しません。HTTP状態と既存ポリシーを調査してください。') from None
            if isinstance(e,urllib.error.HTTPError):
                raise WriteBlocked('HTTP '+str(e.code)+'。全書込みを停止。読戻しで成功分を照合してください。') from None
            raise
        if entries:
            results=data if isinstance(data,list) else [data]
            for (api,row),r in zip(entries,results):
                if r.get('success') and r.get('id'):self.policy.created.setdefault(api,set()).add(r['id'])
            if any(r.get('success') is False for r in results):
                self.policy.stopped=True
                # Return per-record results to permit journaling; all further writes are blocked.
        return data

    def query(self,soql):
        if not re.match(r'^\s*SELECT\b',soql,re.I):raise WriteBlocked('読み取りSELECT以外は使用できません。')
        d=self.request('/services/data/v'+self.version+'/query/?q='+urllib.parse.quote(soql));rows=d['records']
        while not d['done']:
            d=self.request(d['nextRecordsUrl']);rows+=d['records']
        return rows

    def set_password(self,user_id,password):
        return self.request('/services/data/v'+self.version+'/sobjects/User/'+user_id+'/password','POST',{'NewPassword':password})
