import asyncio
import ipaddress

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.firmware.providers import base
from app.firmware.providers.dlink import DlinkFirmwareProvider
from app.main import app
from app import mailer


def test_oversized_request_is_rejected_before_form_parsing():
    with TestClient(app) as client:
        response=client.post("/login",content=b"x"*(settings.max_request_bytes+1),headers={"content-type":"application/x-www-form-urlencoded"})
    assert response.status_code==413
    assert response.json()["error"]=="Тело запроса слишком велико"


def test_dynamic_responses_have_security_and_private_cache_headers():
    with TestClient(app) as client:
        response=client.get("/login")
    assert response.headers["x-content-type-options"]=="nosniff"
    assert response.headers["x-frame-options"]=="DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"]=="no-store"


def test_smtp_rejects_loopback_before_connection(monkeypatch):
    monkeypatch.setattr(mailer.socket,"getaddrinfo",lambda *args,**kwargs:[(2,1,6,"",("127.0.0.1",25))])
    connected=[]
    monkeypatch.setattr(mailer.smtplib,"SMTP",lambda *args,**kwargs:connected.append(args))
    with pytest.raises(mailer.MailDeliveryError,match="запрещённый служебный адрес"):
        mailer._send_email({"host":"mail.internal","port":25,"encryption":"none","username":"","sender_email":"from@example.com","sender_name":"Monitor","recipients":["to@example.com"]},"","Test","Body")
    assert connected==[]


def test_redirect_target_is_validated_before_second_request(monkeypatch):
    class Response:
        status_code=302
        headers={"location":"http://127.0.0.1/internal"}
        encoding="utf-8"
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return None
    class Client:
        calls=0
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return None
        def stream(self,*args,**kwargs):self.calls+=1;return Response()
    client=Client()
    monkeypatch.setattr(base.httpx,"AsyncClient",lambda *args,**kwargs:client)
    def validate(url):
        host=url.split("/",3)[2].split(":",1)[0]
        try:
            if not ipaddress.ip_address(host).is_global:raise ValueError("private target")
        except ValueError as exc:
            if str(exc)=="private target":raise
    with pytest.raises(ValueError,match="private target"):
        asyncio.run(base.fetch_limited("https://vendor.example/firmware",validate))
    assert client.calls==1


def test_dlink_redirect_handler_rejects_target_before_following():
    handler=DlinkFirmwareProvider._SafeRedirectHandler(DlinkFirmwareProvider().validate_source)
    with pytest.raises(ValueError):
        handler.redirect_request(None,None,302,"Found",{},"http://127.0.0.1/internal")
