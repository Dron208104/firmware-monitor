from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.main import app
from app.db import SessionLocal
from app.models import ConnectionProfile,Device

def csrf(client): client.get('/settings');return client.cookies.get('csrf')
def clean():
    with SessionLocal() as db:db.execute(delete(Device));db.execute(delete(ConnectionProfile));db.commit()

def test_delete_free_profile_and_no_secret_in_response():
    clean()
    with SessionLocal() as db:p=ConnectionProfile(name='free',method='snmp',snmp_version='2c',secret_encrypted='cipher');db.add(p);db.commit();pid=p.id
    with TestClient(app) as client:r=client.request('DELETE',f'/api/connection-profiles/{pid}',json={'csrf':csrf(client)});assert r.status_code==200 and 'secret' not in r.text.lower()

def test_delete_used_profile_is_rejected_and_missing_is_404():
    clean()
    with SessionLocal() as db:
        p=ConnectionProfile(name='used',method='snmp',snmp_version='2c',secret_encrypted='cipher');db.add(p);db.flush();db.add(Device(name='d',ip_address='192.0.2.90',vendor='x',model='x',profile_id=p.id));db.commit();pid=p.id
    with TestClient(app) as client:
        token=csrf(client);r=client.request('DELETE',f'/api/connection-profiles/{pid}',json={'csrf':token});assert r.status_code==409 and '1' in r.json()['error'];assert client.request('DELETE','/api/connection-profiles/999999',json={'csrf':token}).status_code==404
