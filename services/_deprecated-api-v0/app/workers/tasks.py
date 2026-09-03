"""Các tác vụ nền — chạy async ngoài request/response chính để không làm chậm API.

Triển khai thật cần thêm: xử lý lỗi/retry chi tiết, logging có cấu trúc, và
locking (vd Redis lock) để tránh 2 worker cùng xử lý 1 payout batch.
"""

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def capture_payment(self, trip_id: str, payment_id: str) -> None:
    """Gọi cổng thanh toán để capture tiền sau khi trip COMPLETED.
    Retry tối đa 3 lần cách nhau 5 phút — nếu vẫn fail, đánh dấu DEBT_PENDING
    (xem tài liệu Payment Flow mục 4, Bước 3)."""
    # TODO: load payment từ DB, gọi PaymentGatewayAdapter.capture(), xử lý kết quả
    pass


@celery_app.task
def run_route_deviation_check(trip_id: str) -> None:
    """Chạy sau mỗi chuyến hoàn thành: so khớp route_polyline_actual với
    route_polyline_optimal, tạo fraud_flags nếu lệch > 1.5x (deck mục 4.2)."""
    # TODO: implement so khớp polyline, ghi FraudFlag nếu vượt ngưỡng
    pass


@celery_app.task
def run_weekly_payout() -> None:
    """Tổng hợp driver_earning_wallet khả dụng của từng tài xế, tạo Payout batch,
    gọi API chuyển khoản ngân hàng (xem tài liệu Payment Flow mục 4, Bước 6)."""
    # TODO: implement batch payout
    pass


@celery_app.task
def check_escrow_refunds() -> None:
    """Kiểm tra tài xế đã ngưng hợp tác đủ 45-60 ngày và không có fraud_flags mở
    -> hoàn trả ký quỹ (deck mục 4.2)."""
    # TODO: implement escrow refund eligibility check
    pass


@celery_app.task
def send_push_notification(user_id: str, title: str, body: str) -> None:
    """Gửi push notification qua FCM — tách riêng để không block luồng chính."""
    # TODO: implement FCM integration
    pass
