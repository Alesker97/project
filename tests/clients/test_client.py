import pytest

from src.clients.client import Client
from src.enums.client_status import ClientStatus
from src.exceptions import InvalidOperationError


@pytest.fixture
def client() -> Client:
    return Client(
        full_name="Алексей Иванов",
        client_id="client-001",
        age=30,
        contacts={
            "phone": "+994501234567",
            "email": "alexey@example.com",
        },
    )


def test_client_creation(client: Client) -> None:
    assert client.full_name == "Алексей Иванов"
    assert client.client_id == "client-001"
    assert client.age == 30
    assert client.contacts == {
        "phone": "+994501234567",
        "email": "alexey@example.com",
    }
    assert client.status is ClientStatus.ACTIVE
    assert client.account_ids == []


def test_client_age_eighteen_is_allowed() -> None:
    client = Client(
        full_name="Анна Иванова",
        client_id="client-002",
        age=18,
        contacts={"phone": "+994501111111"},
    )

    assert client.age == 18


@pytest.mark.parametrize(
    "age",
    [
        17,
        0,
        -1,
        True,
        18.0,
        "18",
        None,
    ],
)
def test_invalid_age_is_rejected(age: object) -> None:
    with pytest.raises(InvalidOperationError):
        Client(
            full_name="Алексей Иванов",
            client_id="client-001",
            age=age,
            contacts={"phone": "+994501234567"},
        )


@pytest.mark.parametrize(
    "full_name",
    [
        "",
        "   ",
        123,
        None,
    ],
)
def test_invalid_full_name_is_rejected(
    full_name: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        Client(
            full_name=full_name,
            client_id="client-001",
            age=30,
            contacts={"phone": "+994501234567"},
        )


@pytest.mark.parametrize(
    "client_id",
    [
        "",
        "   ",
        123,
        None,
    ],
)
def test_invalid_client_id_is_rejected(
    client_id: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        Client(
            full_name="Алексей Иванов",
            client_id=client_id,
            age=30,
            contacts={"phone": "+994501234567"},
        )


@pytest.mark.parametrize(
    "contacts",
    [
        {},
        [],
        {"": "+994501234567"},
        {"phone": ""},
        {"phone": "   "},
        {1: "+994501234567"},
        {"phone": 123},
        None,
    ],
)
def test_invalid_contacts_are_rejected(
    contacts: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        Client(
            full_name="Алексей Иванов",
            client_id="client-001",
            age=30,
            contacts=contacts,
        )


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(InvalidOperationError):
        Client(
            full_name="Алексей Иванов",
            client_id="client-001",
            age=30,
            contacts={"phone": "+994501234567"},
            status="active",
        )


def test_contacts_are_normalized() -> None:
    client = Client(
        full_name="  Алексей Иванов  ",
        client_id="  client-001  ",
        age=30,
        contacts={
            " phone ": " +994501234567 ",
            " email ": " alexey@example.com ",
        },
    )

    assert client.full_name == "Алексей Иванов"
    assert client.client_id == "client-001"
    assert client.contacts == {
        "phone": "+994501234567",
        "email": "alexey@example.com",
    }


def test_contacts_property_returns_copy(client: Client) -> None:
    contacts = client.contacts
    contacts["phone"] = "changed"

    assert client.contacts["phone"] == "+994501234567"


def test_add_account_id(client: Client) -> None:
    client._add_account_id("account-001")

    assert client.account_ids == ["account-001"]


def test_duplicate_account_id_is_rejected(
    client: Client,
) -> None:
    client._add_account_id("account-001")

    with pytest.raises(InvalidOperationError):
        client._add_account_id("account-001")

    assert client.account_ids == ["account-001"]


def test_invalid_account_id_is_rejected(
    client: Client,
) -> None:
    with pytest.raises(InvalidOperationError):
        client._add_account_id("   ")


def test_account_ids_property_returns_copy(
    client: Client,
) -> None:
    client._add_account_id("account-001")
    account_ids = client.account_ids
    account_ids.append("account-002")

    assert client.account_ids == ["account-001"]


def test_set_status(client: Client) -> None:
    client._set_status(ClientStatus.BLOCKED)

    assert client.status is ClientStatus.BLOCKED


def test_set_invalid_status_is_rejected(
    client: Client,
) -> None:
    with pytest.raises(InvalidOperationError):
        client._set_status("blocked")

    assert client.status is ClientStatus.ACTIVE
