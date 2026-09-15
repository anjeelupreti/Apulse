import re

import pytest


def test_valid_incoming_request_id_is_echoed(client):
    response = client.get("/healthz", HTTP_X_REQUEST_ID="pos-device-7.abc_123")
    assert response["X-Request-ID"] == "pos-device-7.abc_123"


@pytest.mark.parametrize("bad", ["", "short", "has spaces in it", "x" * 65, "inject\r\nheader"])
def test_invalid_request_id_is_replaced(client, bad):
    response = client.get("/healthz", HTTP_X_REQUEST_ID=bad)
    assert response["X-Request-ID"] != bad
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])
