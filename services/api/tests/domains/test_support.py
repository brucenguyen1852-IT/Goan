"""Ticket hỗ trợ: SLA, phân công tự động, leo thang, bàn giao ca, mẫu trả lời (P2-08…P2-10).

Bốn cam kết vận hành ở tài liệu phân định §7.5 quyết định file này, và cả bốn đều là thứ chỉ
vỡ ra lúc đông việc — đúng lúc không ai còn thời gian phát hiện bằng mắt:

  1. Mức ưu tiên do LOẠI VẤN ĐỀ quyết định, không do khách tự chọn. Một vụ tai nạn được khách
     đánh dấu "thấp" mà nằm 8 tiếng trong hàng đợi là hỏng theo nghĩa nghiêm trọng nhất.
  2. SLA đo PHẢN HỒI ĐẦU TIÊN. Đo lúc đóng ticket thì mọi chỉ số đều đẹp và không nói gì cả.
  3. Quá hạn phải TỰ leo thang. Chờ người phát hiện nghĩa là chờ khách gọi lần thứ hai.
  4. Agent tắt máy thì ticket QUAY VỀ hàng đợi, không nằm chờ theo người.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.domains.support import service
from app.domains.support.constants import (
    AgentStatus,
    TicketCategory,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    TicketTeam,
)
from app.domains.support.models import AgentPresence, TicketEvent
from tests.conftest import create_driver, create_rider
from tests.domains.test_iam import make_staff


async def _agent(db, *, email: str, team: TicketTeam = TicketTeam.CS, max_chats: int = 5):
    staff = await make_staff(db, email=email, roles=["cs_agent"])
    await service.set_presence(
        db, staff, status=AgentStatus.AVAILABLE, team=team, max_chats=max_chats
    )
    return staff


async def _events(db, ticket) -> list[TicketEventType]:
    rows = (
        (
            await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .order_by(TicketEvent.created_at, TicketEvent.id)
            )
        )
        .scalars()
        .all()
    )
    return [e.event_type for e in rows]


# --- Mức ưu tiên và SLA (P2-08) -------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "category,requested,mong_doi",
    [
        (TicketCategory.SAFETY, TicketPriority.LOW, TicketPriority.URGENT),
        (TicketCategory.PAYMENT, TicketPriority.NORMAL, TicketPriority.HIGH),
        (TicketCategory.FRAUD, TicketPriority.LOW, TicketPriority.HIGH),
        # Khách chọn cao hơn sàn thì giữ nguyên lựa chọn của họ, không kéo xuống.
        (TicketCategory.PAYMENT, TicketPriority.URGENT, TicketPriority.URGENT),
        (TicketCategory.APP_ISSUE, TicketPriority.LOW, TicketPriority.LOW),
    ],
)
def test_muc_uu_tien_nang_theo_loai_van_de_va_khong_bao_gio_ha(category, requested, mong_doi):
    """QA-SUP-01. Khách đánh dấu một vụ tai nạn là "thấp" không làm nó thành việc nhẹ — họ
    không biết cách phân loại của mình ảnh hưởng tới hàng đợi CSKH."""
    assert service.effective_priority(category, requested) is mong_doi


@pytest.mark.unit
def test_han_sla_dung_theo_muc_uu_tien():
    """QA-SUP-02. `urgent` là 2 phút, `low` là 8 giờ — sai bảng này thì mọi thứ phía sau
    (leo thang, báo cáo chất lượng) đều sai theo mà vẫn "chạy"."""
    moc = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)

    assert service.sla_due_at(TicketPriority.URGENT, now=moc) == moc + timedelta(minutes=2)
    assert service.sla_due_at(TicketPriority.HIGH, now=moc) == moc + timedelta(minutes=15)
    assert service.sla_due_at(TicketPriority.NORMAL, now=moc) == moc + timedelta(minutes=60)
    assert service.sla_due_at(TicketPriority.LOW, now=moc) == moc + timedelta(hours=8)


# --- Mở ticket ------------------------------------------------------------------------


@pytest.mark.integration
async def test_mo_ticket_sinh_ma_doc_duoc_va_hoi_thoai_di_kem(db):
    """QA-SUP-03. Khách gọi tổng đài đọc mã, không đọc UUID 36 ký tự."""
    rider = await create_rider(db, phone="0901000051")

    ticket = await service.create_ticket(
        db, user=rider, subject="Bị trừ tiền hai lần", category=TicketCategory.PAYMENT
    )

    assert ticket.code.startswith("GA-") and ticket.code.endswith("0001")
    assert ticket.conversation_id is not None
    assert ticket.team is TicketTeam.FINANCE  # đúng đội theo loại vấn đề
    assert ticket.priority is TicketPriority.HIGH  # dính tiền thì nâng lên
    assert await _events(db, ticket) == [TicketEventType.CREATED]


@pytest.mark.integration
async def test_ma_ticket_tang_dan_trong_ngay(db):
    """Hai ticket cùng ngày không được trùng mã — mã trùng thì tổng đài mở nhầm hồ sơ."""
    rider = await create_rider(db, phone="0901000052")

    a = await service.create_ticket(db, user=rider, subject="Lỗi 1", category=TicketCategory.OTHER)
    b = await service.create_ticket(db, user=rider, subject="Lỗi 2", category=TicketCategory.OTHER)

    assert a.code != b.code
    assert b.code.endswith("0002")


@pytest.mark.integration
async def test_ticket_cua_tai_xe_ghi_dung_loai_chu_the(db):
    """Trộn khách với tài xế vào một cột thì báo cáo "khiếu nại từ tài xế" thành vô nghĩa."""
    driver_user, _ = await create_driver(db, phone="0902000052")

    ticket = await service.create_ticket(
        db, user=driver_user, subject="Chưa nhận được tiền", category=TicketCategory.PAYMENT
    )

    assert ticket.subject_type.value == "driver"


@pytest.mark.integration
async def test_noi_dung_khach_mo_ta_di_thang_vao_hoi_thoai(db):
    """Agent đọc liền mạch trong một màn hình, không phải nhảy giữa ticket và chat."""
    from app.domains.chat.models import Message

    rider = await create_rider(db, phone="0901000053")

    ticket = await service.create_ticket(
        db,
        user=rider,
        subject="Tài xế không đến",
        category=TicketCategory.OTHER,
        body="Em chờ 30 phút rồi ạ",
    )

    tin = (
        (await db.execute(select(Message).where(Message.conversation_id == ticket.conversation_id)))
        .scalars()
        .all()
    )
    assert [m.body for m in tin] == ["Em chờ 30 phút rồi ạ"]


# --- Phân công tự động (P2-09) --------------------------------------------------------


@pytest.mark.integration
async def test_ticket_moi_vao_dung_agent_con_slot(db):
    """QA-SUP-04. DoD của P2-09."""
    rider = await create_rider(db, phone="0901000054")
    agent = await _agent(db, email="cs1@goan.vn")

    ticket = await service.create_ticket(
        db, user=rider, subject="Hỏi về ứng dụng", category=TicketCategory.APP_ISSUE
    )

    assert ticket.assigned_agent_id == agent.id
    assert ticket.status is TicketStatus.ASSIGNED
    presence = (
        await db.execute(select(AgentPresence).where(AgentPresence.agent_id == agent.id))
    ).scalar_one()
    assert presence.active_chats == 1


@pytest.mark.integration
async def test_agent_het_slot_thi_khong_nhan_them(db):
    """QA-SUP-05. Nhét quá trần là cách biến một agent thành nút thắt cho cả hàng đợi."""
    rider = await create_rider(db, phone="0901000055")
    await _agent(db, email="cs2@goan.vn", max_chats=1)

    dau = await service.create_ticket(
        db, user=rider, subject="Việc 1", category=TicketCategory.APP_ISSUE
    )
    sau = await service.create_ticket(
        db, user=rider, subject="Việc 2", category=TicketCategory.APP_ISSUE
    )

    assert dau.assigned_agent_id is not None
    assert sau.assigned_agent_id is None
    assert sau.status is TicketStatus.NEW  # nằm hàng đợi chung, không gán bừa


@pytest.mark.integration
async def test_uu_tien_agent_da_tung_xu_ly_viec_cua_khach_nay(db):
    """QA-SUP-06. Kể lại từ đầu cho người mới là cách nhanh nhất làm khách tức giận thêm
    một lần nữa."""
    rider = await create_rider(db, phone="0901000056")
    quen = await _agent(db, email="cs-quen@goan.vn")

    dau = await service.create_ticket(
        db, user=rider, subject="Lần đầu", category=TicketCategory.APP_ISSUE
    )
    await service.resolve(db, dau, actor=quen, note="Đã hướng dẫn")
    # Người mới rảnh hơn (0 việc) nhưng chưa từng làm việc với khách này.
    await _agent(db, email="cs-moi@goan.vn")

    sau = await service.create_ticket(
        db, user=rider, subject="Lần hai", category=TicketCategory.APP_ISSUE
    )

    assert sau.assigned_agent_id == quen.id


@pytest.mark.integration
async def test_khong_ai_truc_thi_ticket_nam_hang_doi_chung(db):
    """Gán cho người đã tắt máy là ticket biến mất khỏi tầm nhìn của cả đội."""
    rider = await create_rider(db, phone="0901000057")
    staff = await make_staff(db, email="cs-offline@goan.vn", roles=["cs_agent"])
    await service.set_presence(db, staff, status=AgentStatus.OFFLINE)

    ticket = await service.create_ticket(
        db, user=rider, subject="Không ai trực", category=TicketCategory.APP_ISSUE
    )

    assert ticket.assigned_agent_id is None
    assert ticket.status is TicketStatus.NEW


@pytest.mark.integration
async def test_agent_khac_doi_khong_nhan_ticket_cua_doi_minh(db):
    """Đội risk không nhận việc thanh toán: phân sai đội là ticket đi lòng vòng thêm một
    vòng chuyển tay."""
    rider = await create_rider(db, phone="0901000058")
    await _agent(db, email="risk1@goan.vn", team=TicketTeam.RISK)

    ticket = await service.create_ticket(
        db, user=rider, subject="Trừ tiền sai", category=TicketCategory.PAYMENT
    )

    assert ticket.team is TicketTeam.FINANCE
    assert ticket.assigned_agent_id is None


# --- Vòng đời -------------------------------------------------------------------------


@pytest.mark.integration
async def test_nhan_ticket_da_co_nguoi_thi_bi_tu_choi(db):
    """Hai agent bấm nhận cùng lúc: người sau phải biết là mình trượt, không được ghi đè."""
    rider = await create_rider(db, phone="0901000059")
    ticket = await service.create_ticket(
        db, user=rider, subject="Việc chung", category=TicketCategory.OTHER
    )
    a = await make_staff(db, email="cs-a@goan.vn", roles=["cs_agent"])
    b = await make_staff(db, email="cs-b@goan.vn", roles=["cs_agent"])

    await service.claim(db, ticket, a)
    with pytest.raises(ConflictError):
        await service.claim(db, ticket, b)


@pytest.mark.integration
async def test_moc_phan_hoi_dau_chi_ghi_mot_lan(db):
    """QA-SUP-07. Ghi đè ở mỗi lần trả lời sẽ biến "phản hồi đầu" thành "phản hồi cuối" —
    một con số luôn đẹp và hoàn toàn vô nghĩa."""
    rider = await create_rider(db, phone="0901000060")
    agent = await _agent(db, email="cs-ph@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Hỏi nhanh", category=TicketCategory.APP_ISSUE
    )

    await service.record_first_response(db, ticket, agent)
    lan_dau = ticket.first_response_at
    await service.record_first_response(db, ticket, agent)

    assert ticket.first_response_at == lan_dau
    assert (await _events(db, ticket)).count(TicketEventType.FIRST_RESPONSE) == 1


@pytest.mark.integration
async def test_chuyen_doi_thi_tra_ticket_ve_hang_doi_doi_moi(db):
    """Đổi đội mà giữ nguyên người cũ là để ticket nằm ở đội mới nhưng không ai trong đội đó
    thấy mình có trách nhiệm."""
    rider = await create_rider(db, phone="0901000061")
    agent = await _agent(db, email="cs-ch@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Nghi ngờ gian lận", category=TicketCategory.APP_ISSUE
    )
    assert ticket.assigned_agent_id == agent.id

    await service.transfer(
        db, ticket, actor=agent, to_team=TicketTeam.RISK, reason="Có dấu hiệu gian lận"
    )

    assert ticket.team is TicketTeam.RISK
    assert ticket.assigned_agent_id is None
    assert ticket.status is TicketStatus.NEW
    presence = (
        await db.execute(select(AgentPresence).where(AgentPresence.agent_id == agent.id))
    ).scalar_one()
    assert presence.active_chats == 0  # trả slot lại cho người cũ


@pytest.mark.integration
async def test_chuyen_tay_luon_ghi_ly_do(db):
    """QA-SUP-08. Vài ngày sau không ai giải thích được vì sao ticket đi qua bốn người thì
    đó chính là loại ticket khách khiếu nại lên trên."""
    rider = await create_rider(db, phone="0901000062")
    a = await _agent(db, email="cs-x@goan.vn")
    b = await make_staff(db, email="cs-y@goan.vn", roles=["cs_agent"])
    ticket = await service.create_ticket(
        db, user=rider, subject="Chuyển tay", category=TicketCategory.OTHER
    )

    await service.transfer(db, ticket, actor=a, to_agent=b, reason="Bàn giao ca chiều")

    su_kien = (
        (
            await db.execute(
                select(TicketEvent).where(
                    TicketEvent.ticket_id == ticket.id,
                    TicketEvent.event_type == TicketEventType.TRANSFERRED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(su_kien) == 1
    assert su_kien[0].payload["reason"] == "Bàn giao ca chiều"


@pytest.mark.integration
async def test_ket_luan_roi_mo_lai_thi_dem_reopen_va_dat_lai_dong_ho(db):
    """QA-SUP-09. Mở ticket mới thay vì reopen sẽ làm tỷ lệ reopen bằng 0 vĩnh viễn — chỉ số
    đẹp nhất và vô dụng nhất một đội CSKH có thể tự tặng cho mình."""
    rider = await create_rider(db, phone="0901000063")
    agent = await _agent(db, email="cs-re@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Chưa xong", category=TicketCategory.OTHER
    )
    await service.record_first_response(db, ticket, agent)
    await service.resolve(db, ticket, actor=agent, note="Đã xử lý")

    await service.reopen(db, ticket, reason="Khách báo vẫn còn lỗi")

    assert ticket.reopened_count == 1
    assert ticket.resolved_at is None
    assert ticket.first_response_at is None  # vòng khiếu nại này phải được trả lời lại
    assert ticket.status is TicketStatus.ASSIGNED


@pytest.mark.integration
async def test_ticket_chua_ket_luan_thi_khong_mo_lai_duoc(db):
    rider = await create_rider(db, phone="0901000064")
    ticket = await service.create_ticket(
        db, user=rider, subject="Đang chạy", category=TicketCategory.OTHER
    )

    with pytest.raises(ConflictError):
        await service.reopen(db, ticket, reason="nhầm")


# --- Leo thang tự động ----------------------------------------------------------------


@pytest.mark.integration
async def test_qua_han_phan_hoi_dau_thi_tu_leo_thang(db):
    """QA-SUP-10. DoD của P2-08. Chờ người phát hiện nghĩa là chờ khách gọi lần thứ hai."""
    rider = await create_rider(db, phone="0901000065")
    ticket = await service.create_ticket(
        db, user=rider, subject="Xe đâm vào lề", category=TicketCategory.SAFETY
    )
    assert ticket.priority is TicketPriority.URGENT

    sau_3_phut = datetime.now(timezone.utc) + timedelta(minutes=3)
    assert await service.escalate_overdue(db, now=sau_3_phut) == 1

    await db.refresh(ticket)
    assert ticket.status is TicketStatus.ESCALATED
    assert TicketEventType.ESCALATED in await _events(db, ticket)


@pytest.mark.integration
async def test_da_tra_loi_trong_han_thi_khong_leo_thang(db):
    """Cặp của test trên: leo thang cả ticket đã được trả lời thì cs_lead ngập việc giả và
    sẽ ngừng nhìn hàng đợi leo thang."""
    rider = await create_rider(db, phone="0901000066")
    agent = await _agent(db, email="cs-ok@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Xe đâm vào lề", category=TicketCategory.SAFETY
    )
    await service.record_first_response(db, ticket, agent)

    assert (
        await service.escalate_overdue(db, now=datetime.now(timezone.utc) + timedelta(hours=9)) == 0
    )
    await db.refresh(ticket)
    assert ticket.status is not TicketStatus.ESCALATED


@pytest.mark.integration
async def test_ticket_da_ket_luan_khong_bi_leo_thang(db):
    rider = await create_rider(db, phone="0901000067")
    agent = await _agent(db, email="cs-done@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Đã xong", category=TicketCategory.SAFETY
    )
    await service.resolve(db, ticket, actor=agent, note="Xử lý tại chỗ")

    assert (
        await service.escalate_overdue(db, now=datetime.now(timezone.utc) + timedelta(days=1)) == 0
    )


# --- Bàn giao ca ----------------------------------------------------------------------


@pytest.mark.integration
async def test_agent_offline_qua_lau_thi_ticket_quay_ve_hang_doi(db):
    """QA-SUP-11. Hết ca, tắt máy, mất mạng — ticket không được nằm chờ theo người."""
    rider = await create_rider(db, phone="0901000068")
    agent = await _agent(db, email="cs-hetca@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Đang xử lý dở", category=TicketCategory.APP_ISSUE
    )
    assert ticket.assigned_agent_id == agent.id
    await service.set_presence(db, agent, status=AgentStatus.OFFLINE)

    assert await service.release_offline_agents(db) == 1

    await db.refresh(ticket)
    assert ticket.assigned_agent_id is None
    assert ticket.status is TicketStatus.NEW
    assert TicketEventType.RELEASED in await _events(db, ticket)


@pytest.mark.integration
async def test_agent_dang_truc_thi_khong_bi_thu_ticket(db):
    """Cặp của test trên: thu ticket của người đang làm việc là phá đúng ca trực."""
    rider = await create_rider(db, phone="0901000069")
    agent = await _agent(db, email="cs-dangtruc@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Đang xử lý", category=TicketCategory.APP_ISSUE
    )

    assert await service.release_offline_agents(db) == 0

    await db.refresh(ticket)
    assert ticket.assigned_agent_id == agent.id


@pytest.mark.integration
async def test_agent_mat_dau_qua_nguong_thi_cung_bi_thu(db):
    """Mất mạng giữa ca không sinh ra sự kiện "offline" nào — chỉ có dấu vết im lặng."""
    rider = await create_rider(db, phone="0901000070")
    await _agent(db, email="cs-matmang@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Mất mạng", category=TicketCategory.APP_ISSUE
    )

    sau = datetime.now(timezone.utc) + timedelta(minutes=20)
    assert await service.release_offline_agents(db, now=sau) == 1

    await db.refresh(ticket)
    assert ticket.assigned_agent_id is None


# --- Hàng đợi -------------------------------------------------------------------------


@pytest.mark.integration
async def test_hang_doi_sap_theo_han_sla_chu_khong_theo_gio_tao(db):
    """QA-SUP-12. Một ticket `urgent` mở sau vẫn phải đứng trước một ticket `low` mở từ sáng."""
    rider = await create_rider(db, phone="0901000071")
    cham = await service.create_ticket(
        db,
        user=rider,
        subject="Góp ý giao diện",
        category=TicketCategory.APP_ISSUE,
        priority=TicketPriority.LOW,
    )
    gap = await service.create_ticket(
        db, user=rider, subject="Tai nạn", category=TicketCategory.SAFETY
    )

    hang_doi = await service.queue(db)

    assert [t.id for t in hang_doi][:2] == [gap.id, cham.id]


@pytest.mark.integration
async def test_hang_doi_khong_tra_ve_ticket_da_ket_luan(db):
    rider = await create_rider(db, phone="0901000072")
    agent = await _agent(db, email="cs-q@goan.vn")
    ticket = await service.create_ticket(
        db, user=rider, subject="Xong rồi", category=TicketCategory.OTHER
    )
    await service.resolve(db, ticket, actor=agent, note="ok")

    assert [t.id for t in await service.queue(db)] == []


# --- Mẫu trả lời (P2-10) --------------------------------------------------------------


@pytest.mark.integration
async def test_go_tat_ra_mau_tra_loi(db):
    """QA-SUP-13. DoD của P2-10: agent gõ /hoantien ra mẫu trả lời."""
    await service.upsert_canned(
        db,
        team=TicketTeam.CS,
        title="Hướng dẫn hoàn tiền",
        body="Anh/chị vui lòng chờ 3-5 ngày làm việc...",
        shortcut="/hoantien",
    )

    mau = await service.resolve_shortcut(db, team=TicketTeam.CS, shortcut="/hoantien")

    assert mau is not None and mau.title == "Hướng dẫn hoàn tiền"
    # Gõ thiếu dấu / vẫn ra: bắt người ta gõ đúng ký tự đầu là tạo ma sát vô ích.
    assert await service.resolve_shortcut(db, team=TicketTeam.CS, shortcut="hoantien") is not None


@pytest.mark.integration
async def test_mau_tat_khong_con_dung_thi_khong_tra_ve(db):
    """Mẫu cũ ghi sai chính sách mà vẫn gọi ra được là gửi thông tin sai cho hàng nghìn khách."""
    mau = await service.upsert_canned(
        db, team=TicketTeam.CS, title="Cũ", body="Chính sách cũ", shortcut="/cu"
    )
    await service.upsert_canned(
        db, team=TicketTeam.CS, title="Cũ", body="Chính sách cũ", shortcut="/cu", is_active=False
    )

    assert mau.is_active is False
    assert await service.resolve_shortcut(db, team=TicketTeam.CS, shortcut="/cu") is None


@pytest.mark.integration
async def test_mau_cua_doi_khac_khong_lan_sang(db):
    """Câu trả lời của đội tài chính gửi nhầm trong hội thoại kỹ thuật là mất uy tín."""
    await service.upsert_canned(
        db, team=TicketTeam.FINANCE, title="Hoàn tiền", body="...", shortcut="/hoantien"
    )

    assert await service.resolve_shortcut(db, team=TicketTeam.CS, shortcut="/hoantien") is None
    assert await service.resolve_shortcut(db, team=TicketTeam.FINANCE, shortcut="/hoantien")


# --- Quyền ----------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.integration
async def test_agent_chi_doc_duoc_ticket_cua_minh(db):
    """QA-SUP-14. `read_own` không được mở cả hàng đợi: đọc hội thoại của người khác là
    ranh giới giữa "làm việc" và "tò mò"."""
    rider = await create_rider(db, phone="0901000073")
    chu = await _agent(db, email="cs-chu@goan.vn")
    nguoi_khac = await make_staff(db, email="cs-khac@goan.vn", roles=["cs_agent"])
    ticket = await service.create_ticket(
        db, user=rider, subject="Riêng tư", category=TicketCategory.APP_ISSUE
    )
    assert ticket.assigned_agent_id == chu.id

    service.assert_can_read(ticket, chu, read_all=False)  # không ném
    with pytest.raises(PermissionDeniedError):
        service.assert_can_read(ticket, nguoi_khac, read_all=False)
    service.assert_can_read(ticket, nguoi_khac, read_all=True)  # cs_lead thì được


# --- Qua HTTP -------------------------------------------------------------------------


@pytest.mark.api
async def test_khach_mo_ticket_va_agent_xu_ly_tron_mot_vong(db, api_client):
    """QA-SUP-15. Một vòng đầy đủ qua đúng chuỗi middleware thật: mở → nhận → kết luận.

    Test gọi thẳng service không thấy lỗi tầng middleware (phân quyền, khử trùng, audit) —
    mà đó lại là tầng hay hỏng nhất khi thêm endpoint mới.
    """
    from app.core.constants import UserRole
    from app.core.security import create_access_token
    from tests.domains.test_iam import staff_headers

    rider = await create_rider(db, phone="0901000081")
    rider_headers = {
        "Authorization": f"Bearer {create_access_token(str(rider.id), UserRole.RIDER.value)}"
    }
    headers = await staff_headers(db, api_client, roles=["cs_lead"], email="lead@goan.vn")

    mo = await api_client.post(
        "/api/v1/support/tickets",
        headers=rider_headers,
        json={
            "subject": "Bị trừ tiền hai lần",
            "category": "payment",
            "body": "Em bị trừ 2 lần cho chuyến tối qua",
        },
    )
    assert mo.status_code == 201, mo.text
    ticket = mo.json()
    assert ticket["priority"] == "high" and ticket["team"] == "finance"

    hang_doi = await api_client.get("/api/v1/ops/support/queue", headers=headers)
    assert hang_doi.status_code == 200
    assert ticket["id"] in [t["id"] for t in hang_doi.json()]

    nhan = await api_client.post(
        f"/api/v1/ops/support/tickets/{ticket['id']}/claim", headers=headers
    )
    assert nhan.status_code == 200 and nhan.json()["status"] == "assigned"

    ket_luan = await api_client.post(
        f"/api/v1/ops/support/tickets/{ticket['id']}/resolve",
        headers=headers,
        json={"note": "Đã hoàn tiền giao dịch trùng"},
    )
    assert ket_luan.status_code == 200 and ket_luan.json()["status"] == "resolved"

    dau_vet = await api_client.get(
        f"/api/v1/ops/support/tickets/{ticket['id']}/events", headers=headers
    )
    assert [e["event_type"] for e in dau_vet.json()] == ["created", "assigned", "resolved"]


@pytest.mark.security
@pytest.mark.api
async def test_nhan_su_khong_co_quyen_support_bi_tu_choi(db, api_client):
    """QA-SUP-16. Kế toán có token nội bộ hợp lệ nhưng không có việc gì với hàng đợi CSKH."""
    from tests.domains.test_iam import staff_headers

    headers = await staff_headers(db, api_client, roles=["finance_accountant"], email="kt@goan.vn")

    tra_loi = await api_client.get("/api/v1/ops/support/queue", headers=headers)

    assert tra_loi.status_code == 403


@pytest.mark.security
@pytest.mark.api
async def test_agent_khong_tra_cuu_duoc_lich_su_chat_cua_nguoi_khac(db, api_client):
    """QA-SUP-17. Tra cứu lịch sử chat là đọc hội thoại của người khác — đòi `read_all`,
    không phải quyền mặc định của mọi agent."""
    from tests.domains.test_iam import staff_headers

    agent = await staff_headers(db, api_client, roles=["cs_agent"], email="cs-tra@goan.vn")
    lead = await staff_headers(db, api_client, roles=["cs_lead"], email="lead-tra@goan.vn")

    assert (await api_client.get("/api/v1/ops/chat/search", headers=agent)).status_code == 403
    assert (await api_client.get("/api/v1/ops/chat/search", headers=lead)).status_code == 200


@pytest.mark.security
@pytest.mark.api
async def test_khach_khong_thay_ticket_cua_khach_khac(db, api_client):
    """Danh sách ticket luôn lọc theo người đang đăng nhập, không theo tham số client gửi lên."""
    from app.core.constants import UserRole
    from app.core.security import create_access_token

    a = await create_rider(db, phone="0901000082")
    b = await create_rider(db, phone="0901000083")
    await service.create_ticket(db, user=a, subject="Việc của A", category=TicketCategory.OTHER)

    tra_loi = await api_client.get(
        "/api/v1/support/tickets",
        headers={"Authorization": f"Bearer {create_access_token(str(b.id), UserRole.RIDER.value)}"},
    )

    assert tra_loi.status_code == 200
    assert tra_loi.json() == []


@pytest.mark.api
async def test_cskh_tham_gia_hoi_thoai_chuyen_qua_console(db, api_client):
    """QA-SUP-18. DoD của P2-17: agent vào chat chuyến, cả hai bên thấy."""
    from app.core.constants import TripStatus
    from app.domains.chat import service as chat_service
    from tests.conftest import create_trip
    from tests.domains.test_iam import staff_headers

    rider = await create_rider(db, phone="0901000084")
    driver_user, _ = await create_driver(db, phone="0902000084")
    trip = await create_trip(db, rider, driver_user, status=TripStatus.DRIVER_ARRIVING)
    conversation = await chat_service.get_or_create_trip_conversation(
        db, trip_id=trip.id, rider_id=rider.id, driver_id=driver_user.id
    )
    headers = await staff_headers(db, api_client, roles=["cs_lead"], email="lead-join@goan.vn")

    vao = await api_client.post(
        f"/api/v1/ops/chat/conversations/{conversation.id}/join", headers=headers
    )
    assert vao.status_code == 200

    tin = await api_client.get(
        f"/api/v1/ops/chat/conversations/{conversation.id}/messages", headers=headers
    )
    assert tin.status_code == 200
    assert [m["kind"] for m in tin.json()] == ["system"]
    assert "tham gia hội thoại" in tin.json()[0]["body"]
