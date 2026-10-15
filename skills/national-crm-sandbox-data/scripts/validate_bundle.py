"""Offline structural/behavioral checks. Never authenticates or accesses Salesforce."""
import json,hashlib,re,collections,unittest,io,urllib.error
from pathlib import Path
from unittest.mock import patch
from sf_data_guard import ROOT,MutationPolicy,DataOnlyClient,WriteBlocked

def load(n):return json.loads((ROOT/'assets'/n).read_text(encoding='utf-8'))
def config(**kw):
    c={'preflight_complete':True,'unresolved':[],'bundle_sha256':hashlib.sha256((ROOT/'assets/business-records.json').read_bytes()).hexdigest(),'data_write_requested':True,'users_requested':False,'password_setting_requested':False}
    c.update(kw);return c
class Checks(unittest.TestCase):
    def test_data_graph(self):
        rows=load('business-records.json');m=load('manifest.json');external=load('external-references.json');keys={r['key'] for r in rows}
        self.assertEqual(len(keys),1862);self.assertEqual(dict(collections.Counter(r['object'] for r in rows)),m['objects'])
        def walk(v):
            if isinstance(v,dict):
                if '$record' in v:self.assertIn(v['$record'],keys)
                if '$external' in v:self.assertIn(v['$external'],external)
                for x in v.values():walk(x)
            elif isinstance(v,list):
                for x in v:walk(x)
        for r in rows:
            self.assertNotIn('Id',r['values']);self.assertNotIn('OwnerId',r['values']);walk(r['values'])
        accounts={r['key'] for r in rows if r['object']=='Account'}
        for r in rows:
            if r['object']=='RelatedOrganization__c':self.assertIn(r['values']['Account__c']['$record'],accounts)
            if r['object']=='Opportunity':self.assertIn(r['values']['Name'],['融資','債権管理'])
            if r['object']=='Task':self.assertNotIn(r['values'].get('WhatId',{}).get('$record'),accounts)
        for filename,digest in m['baseline_hashes'].items():self.assertEqual(hashlib.sha256((ROOT/'assets'/filename).read_bytes()).hexdigest(),digest)
        for f in load('files.json'):
            self.assertIn(f['publish_to']['$record'],accounts)
            self.assertEqual(hashlib.sha256((ROOT/'assets'/f['path']).read_bytes()).hexdigest(),f['sha256'])
    def test_user_template(self):
        users=load('user-records.json');self.assertEqual(len(users),70)
        self.assertEqual({r['values']['LastName'] for r in users},{'確認用'+str(i) for i in range(1,71)})
        self.assertEqual(dict(collections.Counter(r['values']['ProfileId']['$profile'] for r in users)),load('manifest.json')['optional_users'])
    def test_settings_blocked(self):
        for api in ['Profile','PermissionSet','PermissionSetAssignment','Group','GroupMember','UserRole','SomeConfig__mdt','BranchMaster__c','GeneralPurposeMaster__c']:
            with self.subTest(api=api),self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('POST','/services/data/v68.0/sobjects/'+api,{'Name':'x'})
        for route in ['/services/data/v68.0/tooling/sobjects/ApexClass','/services/data/v68.0/tooling/executeAnonymous','/services/data/v68.0/metadata/deploy','/services/data/v68.0/composite']:
            with self.subTest(route=route),self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('POST',route,{})
    def test_missing_information_stops_all_writes(self):
        p=MutationPolicy(config(unresolved=['担当者が複数件']))
        with self.assertRaises(WriteBlocked):p.authorize('POST','/services/data/v68.0/sobjects/Account',{'Name':'x'})
        p.config['unresolved']=[]
        with self.assertRaises(WriteBlocked):p.authorize('POST','/services/data/v68.0/sobjects/Account',{'Name':'x'})
        self.assertEqual(p.authorize('GET','/services/data/v68.0/query/?q=SELECT+Id+FROM+User'),[])
    def test_existing_data_and_mixed_composite(self):
        with self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('PATCH','/services/data/v68.0/sobjects/Account/001AAAAAAAAAAAAAAA',{'Name':'x'})
        with self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('POST','/services/data/v68.0/composite/sobjects',{'allOrNone':False,'records':[{'attributes':{'type':'Account'},'Name':'x'},{'attributes':{'type':'Profile'},'Name':'x'}]})
        p=MutationPolicy(config());p.created['Account']={'001AAAAAAAAAAAAAAA'}
        self.assertEqual(len(p.authorize('PATCH','/services/data/v68.0/sobjects/Account/001AAAAAAAAAAAAAAA',{'Name':'x'})),1)
    def test_users_and_password_require_separate_requests(self):
        with self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('POST','/services/data/v68.0/sobjects/User',{'LastName':'確認用1'})
        with self.assertRaises(WriteBlocked):MutationPolicy(config(users_requested=True)).authorize('POST','/services/data/v68.0/sobjects/User/005AAAAAAAAAAAAAAA/password',{'NewPassword':'ephemeral-value'})
        p=MutationPolicy(config(password_setting_requested=True,password_targets_verified=True,password_user_ids=['005AAAAAAAAAAAAAAA']))
        p.authorize('POST','/services/data/v68.0/sobjects/User/005AAAAAAAAAAAAAAA/password',{'NewPassword':'ephemeral-value'})
        with self.assertRaises(WriteBlocked):p.authorize('POST','/services/data/v68.0/sobjects/User/005BBBBBBBBBBBBBBB/password',{'NewPassword':'ephemeral-value'})
    def test_existing_updates_are_field_scoped(self):
        sid='001AAAAAAAAAAAAAAA'
        options={'authorized_update_ids':{'Account':[sid]},'authorized_update_fields':{'Account':{sid:['Name']}}}
        self.assertEqual(len(MutationPolicy(config(**options)).authorize('PATCH','/services/data/v68.0/sobjects/Account/'+sid,{'Name':'x'})),1)
        with self.assertRaises(WriteBlocked):MutationPolicy(config(**options)).authorize('PATCH','/services/data/v68.0/sobjects/Account/'+sid,{'Phone':'123'})
        p=MutationPolicy(config(users_requested=True));p.created['User']={'005AAAAAAAAAAAAAAA'}
        with self.assertRaises(WriteBlocked):p.authorize('PATCH','/services/data/v68.0/sobjects/User/005AAAAAAAAAAAAAAA',{'LastName':'x'})
    def test_custom_setting_and_existing_document_blocked(self):
        c=DataOnlyClient.__new__(DataOnlyClient);c.policy=MutationPolicy(config());c.schemas={'Account':{'customSetting':True,'fields':[]}}
        with patch('urllib.request.urlopen') as network:
            with self.assertRaises(WriteBlocked):c.request('/services/data/v68.0/sobjects/Account','POST',{'Name':'x'})
            network.assert_not_called();self.assertTrue(c.policy.stopped)
        with self.assertRaises(WriteBlocked):MutationPolicy(config()).authorize('POST','/services/data/v68.0/sobjects/ContentVersion',{'ContentDocumentId':'069AAAAAAAAAAAAAAA'})
    def test_production_and_wrong_environment_blocked(self):
        from types import SimpleNamespace
        inputs={'target_alias':'unit','expected_org_id':'00DAAAAAAAAAAAAAAA','expected_username':'unit@example.invalid'}
        def auth(url,org_id=inputs['expected_org_id']):
            return SimpleNamespace(returncode=0,stdout=json.dumps({'status':0,'result':{'id':org_id,'username':inputs['expected_username'],'instanceUrl':url,'accessToken':'not-a-real-token'}}))
        with patch('pathlib.Path.read_text',return_value=json.dumps(inputs)):
            for result in [auth('https://unit.my.salesforce.com'),auth('https://unit--test.sandbox.my.salesforce.com','00DBBBBBBBBBBBBBBB')]:
                with patch('subprocess.run',return_value=result),patch.object(DataOnlyClient,'query') as read:
                    with self.assertRaises(WriteBlocked):DataOnlyClient('not-a-real-config')
                    read.assert_not_called()
            with patch('subprocess.run',return_value=auth('https://unit--test.sandbox.my.salesforce.com')),patch.object(DataOnlyClient,'query',return_value=[{'Id':inputs['expected_org_id'],'IsSandbox':False}]):
                with self.assertRaises(WriteBlocked):DataOnlyClient('not-a-real-config')
    def test_password_not_exposed_on_error(self):
        c=DataOnlyClient.__new__(DataOnlyClient);c.version='68.0';c.policy=MutationPolicy(config(password_setting_requested=True,password_targets_verified=True,password_user_ids=['005AAAAAAAAAAAAAAA']));c.url='https://unit--fake.sandbox.my.salesforce.com';c.token='not-a-real-token'
        marker='ephemeral-secret-marker'
        err=urllib.error.HTTPError(c.url,400,'rejected',{},io.BytesIO(marker.encode()))
        with patch('urllib.request.urlopen',side_effect=err):
            with self.assertRaises(WriteBlocked) as raised:c.set_password('005AAAAAAAAAAAAAAA',marker)
            self.assertNotIn(marker,str(raised.exception));self.assertTrue(c.policy.stopped)

if __name__=='__main__':unittest.main(verbosity=2)
