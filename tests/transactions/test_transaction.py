from datetime import datetime
from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.enums.currency import Currency
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction


@pytest.fixture
def sender() -> BankAccount:
    return BankAccount(
        owner="Алексей Иванов",
        balance=Decimal("10000"),
        currency=Currency.RUB,
        account_id="sender-001",
    )

@pytest.fixture
def recipient() -> BankAccount:
    return BankAccount(
        owner="Мария Петрова",
        balance=Decimal("5000"),
        currency=Currency.RUB,
        account_id="recipient-001",
    )

def test_create_transaction(
    sender: BankAccount,
    recipient: BankAccount,
) -> None:
    created_at = datetime(2026, 9, 26, 12, 0)
    scheduled_at = datetime(2026, 9, 26, 13, 0)

    transaction = Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("1500"),
        currency=Currency.RUB,
        sender=sender,
        recipient=recipient,
        transaction_id="transaction-001",
        created_at=created_at,
        scheduled_at=scheduled_at,
    )

    assert transaction.transaction_id == "transaction-001"
    assert transaction.transaction_type is (
        TransactionType.INTERNAL_TRANSFER
    )
    assert transaction.amount == Decimal("1500")
    assert transaction.currency is Currency.RUB
    assert transaction.sender is sender
    assert transaction.recipient is recipient
    assert transaction.commission == Decimal("0.00")
    assert transaction.status is TransactionStatus.PENDING
    assert transaction.failure_reason is None
    assert transaction.created_at == created_at
    assert transaction.scheduled_at == scheduled_at
    assert transaction.processed_at is None
    assert transaction.attempts == 0

def test_generate_transaction_id(
    sender: BankAccount,
    recipient: BankAccount,
) -> None:
    transaction = Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("100"),
        currency=Currency.RUB,
        sender=sender,
        recipient=recipient,
    )

    assert len(transaction.transaction_id) == 8
    assert transaction.transaction_id.isalnum()

@pytest.mark.parametrize(
    "amount",
    [
        Decimal("0"),
        Decimal("-1"),
        "incorrect",
        True,
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_reject_invalid_amount(
    sender: BankAccount,
    recipient: BankAccount,
    amount: Decimal | str | bool,
) -> None:
    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=amount,
            currency=Currency.RUB,
            sender=sender,
            recipient=recipient,
        )

def test_reject_invalid_transaction_type(
    sender: BankAccount,
    recipient: BankAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type="internal_transfer",
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=sender,
            recipient=recipient,
        )

def test_reject_invalid_currency(
    sender: BankAccount,
    recipient: BankAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency="RUB",
            sender=sender,
            recipient=recipient,
        )

def test_reject_same_account(
    sender: BankAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=sender,
            recipient=sender,
        )

def test_reject_accounts_with_same_id(
    sender: BankAccount,
) -> None:
    duplicate_account = BankAccount(
        owner="Другой клиент",
        balance=Decimal("1000"),
        currency=Currency.RUB,
        account_id=sender.account_id,
    )

    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=sender,
            recipient=duplicate_account,
        )

def test_reject_schedule_before_creation(
    sender: BankAccount,
    recipient: BankAccount,
) -> None:
    with pytest.raises(InvalidOperationError):
        Transaction(
            transaction_type=TransactionType.INTERNAL_TRANSFER,
            amount=Decimal("100"),
            currency=Currency.RUB,
            sender=sender,
            recipient=recipient,
            created_at=datetime(2026, 9, 26, 12, 0),
            scheduled_at=datetime(2026, 9, 26, 11, 59),
        )
