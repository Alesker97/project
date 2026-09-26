from datetime import datetime
from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.accounts.investment_account import InvestmentAccount
from src.accounts.premium_account import PremiumAccount
from src.accounts.savings_account import SavingsAccount
from src.banks.bank import Bank
from src.clients.client import Client
from src.enums.account_status import AccountStatus
from src.enums.asset_type import AssetType
from src.enums.client_status import ClientStatus
from src.enums.currency import Currency
from src.exceptions import InvalidOperationError


def create_client(
    client_id: str = "client-001",
    full_name: str = "Алексей Иванов",
) -> Client:
    return Client(
        full_name=full_name,
        client_id=client_id,
        age=30,
        contacts={"phone": "+994501234567"},
    )


def create_account(
    owner: str = "Алексей Иванов",
    account_id: str = "account-001",
    balance: Decimal | int | float = 1000,
    currency: Currency = Currency.RUB,
) -> BankAccount:
    return BankAccount(
        owner=owner,
        balance=balance,
        currency=currency,
        account_id=account_id,
    )


@pytest.fixture
def bank() -> Bank:
    return Bank(
        time_provider=lambda: datetime(
            2026,
            9,
            26,
            12,
            0,
        )
    )


def test_add_client_and_authenticate(bank: Bank) -> None:
    client = create_client()

    bank.add_client(client, "password")

    assert bank.authenticate_client(
        "client-001",
        "password",
    ) is True


def test_duplicate_client_id_is_rejected(bank: Bank) -> None:
    bank.add_client(create_client(), "password")

    with pytest.raises(InvalidOperationError):
        bank.add_client(create_client(), "another-password")


@pytest.mark.parametrize(
    "password",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_invalid_password_is_rejected(
    bank: Bank,
    password: object,
) -> None:
    with pytest.raises(InvalidOperationError):
        bank.add_client(create_client(), password)


def test_open_account(bank: Bank) -> None:
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")
    result = bank.open_account(client.client_id, account)

    assert result == "account-001"
    assert client.account_ids == ["account-001"]
    assert bank.search_accounts(
        client_id=client.client_id
    ) == [account]


def test_open_different_account_types(bank: Bank) -> None:
    client = create_client()
    bank.add_client(client, "password")

    accounts = [
        create_account(account_id="account-001"),
        SavingsAccount(
            owner=client.full_name,
            balance=5000,
            account_id="account-002",
            min_balance=1000,
            monthly_interest_rate=0.01,
        ),
        PremiumAccount(
            owner=client.full_name,
            balance=5000,
            account_id="account-003",
            withdrawal_limit=10000,
            overdraft_limit=1000,
            fixed_commission=100,
        ),
        InvestmentAccount(
            owner=client.full_name,
            balance=5000,
            account_id="account-004",
        ),
    ]

    for account in accounts:
        bank.open_account(client.client_id, account)

    assert client.account_ids == [
        "account-001",
        "account-002",
        "account-003",
        "account-004",
    ]
    assert bank.search_accounts(
        client_id=client.client_id
    ) == accounts


def test_account_owner_must_match_client(bank: Bank) -> None:
    client = create_client()
    account = create_account(owner="Другой владелец")

    bank.add_client(client, "password")

    with pytest.raises(InvalidOperationError):
        bank.open_account(client.client_id, account)

    assert client.account_ids == []


def test_duplicate_account_id_is_rejected(bank: Bank) -> None:
    first_client = create_client()
    second_client = create_client(
        client_id="client-002",
        full_name="Мария Иванова",
    )

    bank.add_client(first_client, "password")
    bank.add_client(second_client, "password")

    bank.open_account(
        first_client.client_id,
        create_account(),
    )

    with pytest.raises(InvalidOperationError):
        bank.open_account(
            second_client.client_id,
            create_account(owner=second_client.full_name),
        )


def test_close_account(bank: Bank) -> None:
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")
    bank.open_account(client.client_id, account)
    bank.close_account(client.client_id, account.account_id)

    assert account.status is AccountStatus.CLOSED
    assert client.account_ids == ["account-001"]


def test_client_cannot_close_another_clients_account(
    bank: Bank,
) -> None:
    first_client = create_client()
    second_client = create_client(
        client_id="client-002",
        full_name="Мария Иванова",
    )
    account = create_account()

    bank.add_client(first_client, "password")
    bank.add_client(second_client, "password")
    bank.open_account(first_client.client_id, account)

    with pytest.raises(InvalidOperationError):
        bank.close_account(
            second_client.client_id,
            account.account_id,
        )

    assert account.status is AccountStatus.ACTIVE


def test_freeze_and_unfreeze_account(bank: Bank) -> None:
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")
    bank.open_account(client.client_id, account)

    bank.freeze_account(account.account_id)
    assert account.status is AccountStatus.FROZEN

    bank.unfreeze_account(account.account_id)
    assert account.status is AccountStatus.ACTIVE


def test_closed_account_cannot_be_frozen_or_unfrozen(
    bank: Bank,
) -> None:
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")
    bank.open_account(client.client_id, account)
    bank.close_account(client.client_id, account.account_id)

    with pytest.raises(InvalidOperationError):
        bank.freeze_account(account.account_id)

    with pytest.raises(InvalidOperationError):
        bank.unfreeze_account(account.account_id)

    assert account.status is AccountStatus.CLOSED


def test_three_failed_attempts_block_client(bank: Bank) -> None:
    client = create_client()
    bank.add_client(client, "password")

    assert bank.authenticate_client(
        client.client_id,
        "wrong-1",
    ) is False
    assert bank.authenticate_client(
        client.client_id,
        "wrong-2",
    ) is False
    assert bank.authenticate_client(
        client.client_id,
        "wrong-3",
    ) is False

    assert client.status is ClientStatus.BLOCKED
    assert bank.authenticate_client(
        client.client_id,
        "password",
    ) is False
    assert len(bank.suspicious_actions) == 3


def test_successful_authentication_resets_attempts(
    bank: Bank,
) -> None:
    client = create_client()
    bank.add_client(client, "password")

    bank.authenticate_client(client.client_id, "wrong-1")
    bank.authenticate_client(client.client_id, "wrong-2")

    assert bank.authenticate_client(
        client.client_id,
        "password",
    ) is True

    bank.authenticate_client(client.client_id, "wrong-3")
    bank.authenticate_client(client.client_id, "wrong-4")

    assert client.status is ClientStatus.ACTIVE
    assert bank.authenticate_client(
        client.client_id,
        "password",
    ) is True


def test_failed_authentication_is_suspicious(
    bank: Bank,
) -> None:
    client = create_client()
    bank.add_client(client, "password")

    bank.authenticate_client(client.client_id, "wrong")

    assert bank.suspicious_actions == [
        {
            "client_id": "client-001",
            "action": "failed_authentication",
            "timestamp": datetime(
                2026,
                9,
                26,
                12,
                0,
            ),
        }
    ]


def test_night_operation_is_rejected() -> None:
    bank = Bank(
        time_provider=lambda: datetime(
            2026,
            9,
            26,
            2,
            0,
        )
    )
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")

    with pytest.raises(InvalidOperationError):
        bank.open_account(client.client_id, account)

    assert client.account_ids == []
    assert bank.search_accounts() == []
    assert bank.suspicious_actions == [
        {
            "client_id": "client-001",
            "action": "night_open_account",
            "timestamp": datetime(
                2026,
                9,
                26,
                2,
                0,
            ),
        }
    ]


def test_operation_at_five_is_allowed() -> None:
    bank = Bank(
        time_provider=lambda: datetime(
            2026,
            9,
            26,
            5,
            0,
        )
    )
    client = create_client()
    account = create_account()

    bank.add_client(client, "password")
    bank.open_account(client.client_id, account)

    assert client.account_ids == ["account-001"]


def test_search_accounts(bank: Bank) -> None:
    first_client = create_client()
    second_client = create_client(
        client_id="client-002",
        full_name="Мария Иванова",
    )
    first_account = create_account(
        account_id="account-001",
        currency=Currency.RUB,
    )
    second_account = create_account(
        account_id="account-002",
        currency=Currency.USD,
    )
    third_account = create_account(
        owner=second_client.full_name,
        account_id="account-003",
        currency=Currency.RUB,
    )

    bank.add_client(first_client, "password")
    bank.add_client(second_client, "password")
    bank.open_account(first_client.client_id, first_account)
    bank.open_account(first_client.client_id, second_account)
    bank.open_account(second_client.client_id, third_account)
    bank.freeze_account(third_account.account_id)

    assert bank.search_accounts(
        client_id=first_client.client_id
    ) == [
        first_account,
        second_account,
    ]
    assert bank.search_accounts(
        status=AccountStatus.FROZEN
    ) == [third_account]
    assert bank.search_accounts(
        currency=Currency.RUB
    ) == [
        first_account,
        third_account,
    ]
    assert bank.search_accounts(
        client_id=second_client.client_id,
        status=AccountStatus.FROZEN,
        currency=Currency.RUB,
    ) == [third_account]


def test_get_total_balance(bank: Bank) -> None:
    client = create_client()
    rub_account = create_account(
        account_id="account-001",
        balance=1000,
        currency=Currency.RUB,
    )
    usd_account = create_account(
        account_id="account-002",
        balance=500,
        currency=Currency.USD,
    )
    investment_account = InvestmentAccount(
        owner=client.full_name,
        balance=3000,
        currency=Currency.RUB,
        account_id="account-003",
    )

    investment_account.invest(
        asset_type=AssetType.STOCKS,
        amount=2000,
    )

    bank.add_client(client, "password")
    bank.open_account(client.client_id, rub_account)
    bank.open_account(client.client_id, usd_account)
    bank.open_account(client.client_id, investment_account)

    assert bank.get_total_balance() == {
        Currency.RUB: Decimal("2000"),
        Currency.USD: Decimal("500"),
        Currency.EUR: Decimal("0"),
        Currency.KZT: Decimal("0"),
        Currency.CNY: Decimal("0"),
    }


def test_get_clients_ranking(bank: Bank) -> None:
    first_client = create_client()
    second_client = create_client(
        client_id="client-002",
        full_name="Мария Иванова",
    )
    third_client = create_client(
        client_id="client-003",
        full_name="Иван Петров",
    )

    bank.add_client(first_client, "password")
    bank.add_client(second_client, "password")
    bank.add_client(third_client, "password")

    bank.open_account(
        first_client.client_id,
        create_account(
            account_id="account-001",
            balance=3000,
        ),
    )
    bank.open_account(
        second_client.client_id,
        create_account(
            owner=second_client.full_name,
            account_id="account-002",
            balance=2500,
        ),
    )
    bank.open_account(
        third_client.client_id,
        create_account(
            owner=third_client.full_name,
            account_id="account-003",
            balance=5000,
            currency=Currency.USD,
        ),
    )

    ranking = bank.get_clients_ranking(Currency.RUB)

    assert ranking == [
        (first_client, Decimal("3000")),
        (second_client, Decimal("2500")),
        (third_client, Decimal("0")),
    ]
