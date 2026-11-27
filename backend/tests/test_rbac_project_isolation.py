from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.api import routes
from app.core.security import create_access_token, hash_password
from app.models.entities import MigrationProject, MigrationProjectMember, User


def _make_user(db, uid_val: str, username: str, role: str = "ENGINEER", email: str | None = None):
    u = User(
        id=uid_val,
        username=username,
        email=email or username,
        password_hash=hash_password("Strong-Password-123!"),
        role=role,
        is_verified=True,
    )
    db.add(u)
    db.commit()
    return {"Authorization": "Bearer " + create_access_token(username, role)}


def test_self_registered_user_defaults_to_engineer_not_admin(client, db, monkeypatch):
    from app.services import email_service
    sender = AsyncMock(return_value=(True, "ok"))
    monkeypatch.setattr(email_service, "send_otp_email", sender)

    res = client.post("/api/register/request-otp", json={"email": "newdev@example.test"})
    assert res.status_code == 200
    code = sender.call_args.args[1]

    proof = client.post("/api/register/verify-otp", json={"email": "newdev@example.test", "otp": code}).json()["verification_token"]
    reg = client.post("/api/register/set-password", json={
        "email": "newdev@example.test",
        "password": "Strong-Password-123!",
        "verification_token": proof,
    })
    assert reg.status_code == 200
    assert reg.json()["role"] == "ENGINEER"

    # ENGINEER cannot access global admin user management endpoints
    headers = {"Authorization": "Bearer " + reg.json()["access_token"]}
    assert client.get("/api/users", headers=headers).status_code == 403


def test_strict_project_privacy_blocks_other_users_including_admins(client, db):
    alice = _make_user(db, "U_ALICE", "alice@example.test", role="ENGINEER")
    bob = _make_user(db, "U_BOB", "bob@example.test", role="ENGINEER")
    other_admin = _make_user(db, "U_ADM2", "admin2@example.test", role="ADMIN")

    alice_prj = client.post("/api/projects", headers=alice, json={"name": "Alice Secret"}).json()
    pid = alice_prj["id"]
    assert alice_prj["visibility"] == "PRIVATE"
    assert alice_prj["my_role"] == "OWNER"

    # Bob and even another ADMIN cannot see Alice's project in list
    assert all(p["id"] != pid for p in client.get("/api/projects", headers=bob).json())
    assert all(p["id"] != pid for p in client.get("/api/projects", headers=other_admin).json())

    # Direct API access to Alice's project is blocked (404) for Bob AND other_admin
    for unauthorized in (bob, other_admin):
        assert client.get(f"/api/projects/{pid}/sources", headers=unauthorized).status_code == 404
        assert client.get(f"/api/projects/{pid}/dashboard", headers=unauthorized).status_code == 404
        assert client.get(f"/api/projects/{pid}/databricks/configuration", headers=unauthorized).status_code == 404
        assert client.get(f"/api/system/health?project_id={pid}", headers=unauthorized).status_code == 404
        assert client.post(
            f"/api/projects/{pid}/sources",
            headers=unauthorized,
            json={"profile_name": "p", "server_name": "s", "database_name": "d"},
        ).status_code == 404
        assert client.delete(f"/api/projects/{pid}", headers=unauthorized).status_code == 404


def test_same_project_name_allowed_across_different_owners(client, db):
    alice = _make_user(db, "U_ALICE2", "alice2@example.test", role="ENGINEER")
    bob = _make_user(db, "U_BOB2", "bob2@example.test", role="ENGINEER")

    p_alice = client.post("/api/projects", headers=alice, json={"name": "Sales"}).json()
    p_bob = client.post("/api/projects", headers=bob, json={"name": "Sales"}).json()

    assert p_alice["id"] != p_bob["id"]
    assert p_alice["name"] == "Sales"
    assert p_bob["name"] == "Sales"
    assert [p["id"] for p in client.get("/api/projects", headers=alice).json()] == [p_alice["id"]]
    assert [p["id"] for p in client.get("/api/projects", headers=bob).json()] == [p_bob["id"]]


def test_explicit_project_sharing_rbac_viewer_editor_owner(client, db):
    alice = _make_user(db, "U_ALICE3", "alice3@example.test", role="ENGINEER")
    bob = _make_user(db, "U_BOB3", "bob3@example.test", role="ENGINEER")
    carol = _make_user(db, "U_CAROL3", "carol3@example.test", role="ENGINEER")

    pid = client.post("/api/projects", headers=alice, json={"name": "Shared Project"}).json()["id"]

    # Non-owner cannot invite members
    assert client.post(
        f"/api/projects/{pid}/members",
        headers=bob,
        json={"user_identifier": "carol3@example.test", "project_role": "VIEWER"},
    ).status_code == 404

    # Alice shares with Bob as VIEWER and Carol as EDITOR
    add_bob = client.post(
        f"/api/projects/{pid}/members",
        headers=alice,
        json={"user_identifier": "bob3@example.test", "project_role": "VIEWER"},
    )
    assert add_bob.status_code == 200
    assert add_bob.json()["project_role"] == "VIEWER"
    assert add_bob.json()["visibility"] == "SHARED"

    add_carol = client.post(
        f"/api/projects/{pid}/members",
        headers=alice,
        json={"user_identifier": "carol3@example.test", "project_role": "EDITOR"},
    )
    assert add_carol.status_code == 200

    # Bob (VIEWER) can read, CANNOT mutate or delete
    bob_projects = client.get("/api/projects", headers=bob).json()
    assert len(bob_projects) == 1 and bob_projects[0]["my_role"] == "VIEWER" and bob_projects[0]["is_shared"] is True
    assert client.get(f"/api/projects/{pid}/sources", headers=bob).status_code == 200
    assert client.post(
        f"/api/projects/{pid}/sources",
        headers=bob,
        json={"profile_name": "p", "server_name": "s", "database_name": "d"},
    ).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=bob).status_code == 403

    # Carol (EDITOR) can read and create sources, CANNOT delete project or manage members
    assert client.post(
        f"/api/projects/{pid}/sources",
        headers=carol,
        json={"profile_name": "p", "server_name": "s", "database_name": "d"},
    ).status_code == 200
    assert client.post(
        f"/api/projects/{pid}/members",
        headers=carol,
        json={"user_identifier": "other@example.test", "project_role": "VIEWER"},
    ).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=carol).status_code == 403

    # Alice revokes Bob's access -> Bob is blocked (404) again
    member_id = add_bob.json()["id"]
    assert client.delete(f"/api/projects/{pid}/members/{member_id}", headers=alice).status_code == 200
    assert client.get(f"/api/projects/{pid}/sources", headers=bob).status_code == 404

    # Alice sets project back to PRIVATE -> Carol is also removed
    priv = client.patch(f"/api/projects/{pid}/privacy", headers=alice, json={"visibility": "PRIVATE"})
    assert priv.status_code == 200 and priv.json()["visibility"] == "PRIVATE"
    assert client.get(f"/api/projects/{pid}/sources", headers=carol).status_code == 404


def test_shared_email_isolates_projects_per_browser_workspace(client, db):
    db.add(User(
        id="U_SHARED",
        username="vtabsquare@gmail.com",
        email="vtabsquare@gmail.com",
        password_hash=hash_password("Shared-Password-123!"),
        role="ENGINEER",
        is_verified=True,
    ))
    db.commit()

    login_1 = client.post(
        "/api/login",
        headers={"X-Workspace-Id": "ws_browser_1"},
        json={"username": "vtabsquare@gmail.com", "password": "Shared-Password-123!"},
    )
    login_2 = client.post(
        "/api/login",
        headers={"X-Workspace-Id": "ws_browser_2"},
        json={"username": "vtabsquare@gmail.com", "password": "Shared-Password-123!"},
    )
    assert login_1.status_code == 200 and login_2.status_code == 200

    h1 = {"Authorization": "Bearer " + login_1.json()["access_token"], "X-Workspace-Id": "ws_browser_1"}
    h2 = {"Authorization": "Bearer " + login_2.json()["access_token"], "X-Workspace-Id": "ws_browser_2"}

    # Both users can even create projects with the same name using the same email
    p1 = client.post("/api/projects", headers=h1, json={"name": "Sales"}).json()
    p2 = client.post("/api/projects", headers=h2, json={"name": "Sales"}).json()
    assert p1["id"] != p2["id"]

    # Browser 1 only sees p1; Browser 2 only sees p2
    assert [p["id"] for p in client.get("/api/projects", headers=h1).json()] == [p1["id"]]
    assert [p["id"] for p in client.get("/api/projects", headers=h2).json()] == [p2["id"]]

    # Cross-browser access using the same email is strictly blocked (404)
    assert client.get(f"/api/projects/{p2['id']}/sources", headers=h1).status_code == 404
    assert client.get(f"/api/projects/{p1['id']}/sources", headers=h2).status_code == 404
    assert client.delete(f"/api/projects/{p1['id']}", headers=h2).status_code == 404
    assert client.delete(f"/api/projects/{p2['id']}", headers=h1).status_code == 404

    # Re-logging in on Browser 1 keeps Browser 1's projects
    relogin_1 = client.post(
        "/api/login",
        headers={"X-Workspace-Id": "ws_browser_1"},
        json={"username": "vtabsquare@gmail.com", "password": "Shared-Password-123!"},
    )
    h1_again = {"Authorization": "Bearer " + relogin_1.json()["access_token"], "X-Workspace-Id": "ws_browser_1"}
    assert [p["id"] for p in client.get("/api/projects", headers=h1_again).json()] == [p1["id"]]
