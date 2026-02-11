from datetime import date, time

from app.models import Meeting


def test_admin_meetings_sorted_by_date_then_time(db_session, auth_client, admin_user):
    db_session.add_all(
        [
            Meeting(
                title="Late Meeting",
                admin_id=admin_user.id,
                meeting_date=date(2026, 3, 2),
                start_time=time(15, 0),
                end_time=time(16, 0),
            ),
            Meeting(
                title="Early Meeting",
                admin_id=admin_user.id,
                meeting_date=date(2026, 3, 1),
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
            Meeting(
                title="No Date Meeting",
                admin_id=admin_user.id,
            ),
        ]
    )
    db_session.commit()

    response = auth_client.get("/admin/meetings")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    early_pos = html.find("Early Meeting")
    late_pos = html.find("Late Meeting")
    no_date_pos = html.find("No Date Meeting")
    assert -1 not in (early_pos, late_pos, no_date_pos)
    assert early_pos < late_pos < no_date_pos


def test_meeting_detail_for_other_admin_returns_403(
    db_session, auth_client, other_admin_user
):
    meeting = Meeting(
        title="Other Admin Meeting",
        admin_id=other_admin_user.id,
    )
    db_session.add(meeting)
    db_session.commit()

    response = auth_client.get(f"/admin/meetings/{meeting.id}")
    assert response.status_code == 403


def test_create_meeting_schedule_validation_returns_single_error(auth_client):
    response = auth_client.post(
        "/admin/meetings/new",
        data={
            "title": "Bad Schedule Meeting",
            "start_time": "16:00",
            "end_time": "15:00",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert (
        payload["error"] == "Meeting date is required when start/end time is set."
    )
