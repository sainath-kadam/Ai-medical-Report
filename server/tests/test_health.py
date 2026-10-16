async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


async def test_health_db_runs_a_query(client):
    response = await client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok", "database": "ok"}
