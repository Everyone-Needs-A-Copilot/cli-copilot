import asyncio
import json

from copilot_cli.services.infisical.core.exceptions import APIError
from copilot_cli.services.infisical.core.provision import provision_machine_identity


class FakeClient:
    def __init__(self):
        self.identities = []
        self.roles = []
        self.memberships = []
        self.calls = []
        self.revoked = []

    async def get_org_id(self, hint):
        return "org-1"

    async def list_identities(self, org_id):
        return self.identities

    async def list_project_roles(self, project_id):
        return self.roles

    async def list_identity_memberships(self, project_id):
        return self.memberships

    async def create_identity(self, name, org_id, role):
        self.calls.append(("create-identity", role))
        identity = {"id": "identity-1", "name": name}
        self.identities.append(identity)
        return identity

    async def create_project_role(self, project_id, **kwargs):
        self.calls.append(("create-role", kwargs))
        role = {"slug": kwargs["slug"], "permissions": kwargs["permissions"]}
        self.roles.append(role)
        return role

    async def add_identity_membership(self, project_id, identity_id, role_slug):
        self.calls.append(("add-membership", identity_id, role_slug))
        self.memberships.append(
            {"identityId": identity_id, "roles": [{"customRoleSlug": role_slug}]}
        )
        return {"id": "membership-1"}

    async def get_universal_auth(self, identity_id):
        self.calls.append(("get-auth", identity_id))
        raise APIError("missing", 404)

    async def attach_universal_auth(self, identity_id):
        self.calls.append(("attach-auth", identity_id))
        return {"clientId": "client-id-secret-zero"}

    async def create_universal_auth_client_secret(self, identity_id, description):
        self.calls.append(("create-secret", identity_id))
        return {
            "clientSecret": "NEVER-RETURN-THIS",
            "clientSecretData": {"id": "secret-1"},
        }

    async def revoke_universal_auth_client_secret(self, identity_id, secret_id):
        self.revoked.append((identity_id, secret_id))
        return {}


def run(client, **kwargs):
    return asyncio.run(
        provision_machine_identity(
            client,
            project_id="project-1",
            environment="prod",
            secret_path="/shared",
            name="device-test",
            **kwargs,
        )
    )


def test_plan_is_read_only_and_describes_exact_scope():
    client = FakeClient()
    report = run(client, read_credential=lambda name: None)
    assert report["result"] == "changes-required"
    assert report["scope"] == {
        "environment": "prod",
        "secret_path": "/shared",
        "access": "read",
    }
    assert client.calls == []


def test_apply_creates_no_access_identity_scoped_role_and_keychain_credentials():
    client = FakeClient()
    stored = {}

    def write(name, value):
        stored[name] = value
        return True

    report = run(
        client,
        apply=True,
        read_credential=lambda name: None,
        write_credential=write,
    )
    assert report["result"] == "applied"
    assert ("create-identity", "no-access") in client.calls
    role_call = next(call for call in client.calls if call[0] == "create-role")
    assert role_call[1]["permissions"] == [
        {
            "subject": "secrets",
            "action": "read",
            "conditions": {"environment": "prod", "secretPath": "/shared"},
        }
    ]
    assert stored == {
        "INFISICAL_CLIENT_ID": "client-id-secret-zero",
        "INFISICAL_CLIENT_SECRET": "NEVER-RETURN-THIS",
    }
    assert "NEVER-RETURN-THIS" not in json.dumps(report)
    assert "client-id-secret-zero" not in json.dumps(report)


def test_existing_ready_identity_is_reused_without_mutation():
    client = FakeClient()
    client.identities = [{"identity": {"id": "identity-1", "name": "device-test"}}]
    from copilot_cli.services.infisical.core.provision import _role_slug

    role_slug = _role_slug("prod", "/shared")
    client.roles = [{"slug": role_slug}]
    client.memberships = [
        {"identityId": "identity-1", "roles": [{"customRoleSlug": role_slug}]}
    ]
    report = run(client, apply=True, read_credential=lambda name: "present")
    assert report["result"] == "applied"
    assert client.calls == []


def test_different_existing_role_policy_blocks():
    client = FakeClient()
    from copilot_cli.services.infisical.core.provision import _role_slug

    client.roles = [{"slug": _role_slug("prod", "/shared"), "permissions": []}]
    report = run(client, read_credential=lambda name: None)
    assert report["result"] == "blocked"
    assert client.calls == []


def test_incomplete_existing_keychain_pair_blocks_without_overwrite():
    client = FakeClient()
    report = run(
        client,
        apply=True,
        read_credential=lambda name: "existing" if name == "INFISICAL_CLIENT_ID" else None,
        write_credential=lambda name, value: (_ for _ in ()).throw(AssertionError("write")),
    )
    assert report["result"] == "blocked"
    assert client.calls == []


def test_keychain_write_failure_revokes_new_secret_and_redacts_report():
    client = FakeClient()
    report = run(
        client,
        apply=True,
        read_credential=lambda name: None,
        write_credential=lambda name, value: False,
    )
    assert report["result"] == "blocked"
    assert client.revoked == [("identity-1", "secret-1")]
    assert "NEVER-RETURN-THIS" not in json.dumps(report)
