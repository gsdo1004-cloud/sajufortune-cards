import pytest
import zodiac_instagram as zi

class Response:
    content=b"{}"
    status_code=200
    def json(self):
        return {"id":"17841448828636115","username":"gsdo10042026","media_count":2}

def test_unified_preflight_uses_safe_fields_and_checks_username(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_USER_ID","17841448828636115")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN","test-token-not-real")
    monkeypatch.setenv("INSTAGRAM_EXPECTED_USERNAME","gsdo10042026")
    monkeypatch.setattr(zi,"IG_API_MODE","unified")
    monkeypatch.setattr(zi,"IG","https://graph.facebook.com/v27.0")
    def get(url,params,timeout):
        assert url=="https://graph.facebook.com/v27.0/17841448828636115"
        assert params["fields"]=="id,username,media_count"
        assert timeout==30
        return Response()
    monkeypatch.setattr(zi.requests,"get",get)
    assert zi.preflight() is True

def test_unified_preflight_rejects_wrong_account_id(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_USER_ID","17841448828636115")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN","test-token-not-real")
    monkeypatch.setenv("INSTAGRAM_EXPECTED_USERNAME","gsdo10042026")
    monkeypatch.setattr(zi,"IG_API_MODE","unified")
    class BadResponse(Response):
        def json(self):
            return {"id":"123456789","username":"gsdo10042026"}
    monkeypatch.setattr(zi.requests,"get",lambda *a,**k:BadResponse())
    with pytest.raises(RuntimeError,match="ID mismatch"):
        zi.preflight()
