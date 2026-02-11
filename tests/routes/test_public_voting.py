def test_voter_dashboard_invalid_code_renders_invalid_page(client):
    response = client.get("/vote/INVALID01")
    assert response.status_code == 200
    html = response.get_data(as_text=True).lower()
    assert "invalid voting link" in html
