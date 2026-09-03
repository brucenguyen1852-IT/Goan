"""Số liệu Prometheus và trace OpenTelemetry (PRD-OPS-07, PRD-OPS-08).

Vì sao bộ test này tồn tại: số liệu quan sát hệ thống là thứ không ai nhìn cho tới lúc có sự
cố — nếu nó hỏng thì hỏng âm thầm. Hai thứ dễ hỏng nhất được chốt ở đây:

  1. Nhãn `path` bị lấy nguyên đường dẫn thật thay vì template route. Lúc đó mỗi UUID chuyến
     thành một chuỗi thời gian riêng, Prometheus phình bộ nhớ rồi chết. Đây là lỗi kinh điển
     và không có test thì không ai phát hiện cho tới khi production sập.
  2. Thiếu gói OpenTelemetry mà vẫn đặt endpoint thì app phải chạy tiếp, không được sập.
"""

import importlib.util
import uuid

import pytest

from app.config import settings
from app.core import metrics


async def _scrape(api_client) -> str:
    response = await api_client.get("/metrics")
    assert response.status_code == 200
    return response.text


@pytest.mark.api
async def test_metrics_tra_ve_dinh_dang_phoi_bay_cua_prometheus(api_client):
    response = await api_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "goan_http_requests_total" in response.text
    assert "goan_app_info" in response.text


@pytest.mark.api
async def test_nhan_path_la_template_route_chu_khong_phai_id_that(api_client):
    """Nếu test này đỏ nghĩa là mỗi chuyến sinh ra một chuỗi thời gian riêng → Prometheus chết."""
    trip_id = uuid.uuid4()

    # Không cần token: request bị chặn ở tầng auth vẫn phải được đếm, và vẫn phải gắn đúng nhãn.
    await api_client.get(f"/api/v1/trips/{trip_id}")
    body = await _scrape(api_client)

    assert 'path="/api/v1/trips/{trip_id}"' in body
    assert str(trip_id) not in body


@pytest.mark.api
async def test_duong_dan_khong_khop_route_nao_gom_vao_unmatched(api_client):
    """Bot quét đường dẫn ngẫu nhiên không được phép sinh nhãn mới cho mỗi lần quét."""
    duong_dan_bia = f"/khong-ton-tai-{uuid.uuid4().hex}"

    await api_client.get(duong_dan_bia)
    body = await _scrape(api_client)

    assert f'path="{metrics.UNMATCHED}"' in body
    assert duong_dan_bia not in body


@pytest.mark.api
async def test_metrics_khong_tu_dem_chinh_no(api_client):
    """Scrape mỗi 15 giây mà tự đếm thì số liệu chỉ toàn tiếng ồn của chính nó."""
    await api_client.get("/metrics")
    body = await _scrape(api_client)

    assert 'path="/metrics"' not in body


@pytest.mark.api
async def test_dem_ca_request_bi_tu_choi(api_client):
    """Request 401/403 vẫn phải vào số liệu — đó chính là thứ cần nhìn khi bị dò tài khoản."""
    before = await _scrape(api_client)
    await api_client.post("/api/v1/trips", json={})
    after = await _scrape(api_client)

    assert after != before
    assert 'path="/api/v1/trips"' in after


@pytest.mark.security
@pytest.mark.api
async def test_dat_metrics_token_thi_khong_co_token_la_401(api_client, monkeypatch):
    """/metrics để lộ danh sách đường dẫn và tần suất gọi, production phải khoá lại được."""
    monkeypatch.setattr(settings, "METRICS_TOKEN", "token-bi-mat")

    khong_token = await api_client.get("/metrics")
    sai_token = await api_client.get("/metrics", headers={"Authorization": "Bearer sai"})
    dung_token = await api_client.get("/metrics", headers={"Authorization": "Bearer token-bi-mat"})

    assert khong_token.status_code == 401
    assert sai_token.status_code == 401
    assert dung_token.status_code == 200


@pytest.mark.unit
def test_route_label_tra_unmatched_khi_scope_chua_co_route():
    class _Req:
        scope: dict = {}

    assert metrics.route_label(_Req()) == metrics.UNMATCHED


@pytest.mark.unit
def test_khong_dat_endpoint_thi_tracing_tat_han():
    from fastapi import FastAPI

    from app.core.observability import setup_tracing

    assert setup_tracing(FastAPI()) is False


@pytest.mark.unit
def test_dat_endpoint_nhung_thieu_goi_otel_thi_canh_bao_chu_khong_sap(monkeypatch, caplog):
    """Mất trace là chuyện phải sửa; làm sập app vì thiếu một gói quan sát thì tệ hơn nhiều."""
    if importlib.util.find_spec("opentelemetry") is not None:
        pytest.skip("Môi trường này đã cài OpenTelemetry — nhánh thiếu gói không chạy được")

    from fastapi import FastAPI

    from app.core.observability import setup_tracing

    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318/v1/traces")

    with caplog.at_level("WARNING"):
        assert setup_tracing(FastAPI()) is False
    assert "OpenTelemetry" in caplog.text
