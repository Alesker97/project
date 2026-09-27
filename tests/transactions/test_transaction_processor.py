from datetime import datetime
from decimal import Decimal
import pytest

from src.accounts.bank_account import BankAccount
from src.accounts.premium_account import PremiumAccount
from src.enums.account_status import AccountStatus
from src.enums.currency import Currency
from src.enums.transaction_priority import TransactionPriority
from src.enums.transaction_status import TransactionStatus
from src.enums.transaction_type import TransactionType
from src.exceptions import InvalidOperationError
from src.transactions.transaction import Transaction
from src.transactions.transaction_processor import TransactionProcessor
from src.transactions.transaction_queue import TransactionQueue


CURRENT_TIME = datetime(2026, 9, 26, 12, 0)


def create_account(
    account_id: str,
    balance: Decimal,
    currency: Currency = Currency.RUB,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> BankAccount:
    return BankAccount(
        owner=account_id,
        balance=balance,
        currency=currency,
        account_id=account_id,
        status=status,
    )


def create_transaction(
    transaction_id: str,
    sender: BankAccount,
    recipient: BankAccount,
    amount: Decimal = Decimal("100"),
    currency: Currency = Currency.RUB,
    transaction_type: TransactionType = (
        TransactionType.INTERNAL_TRANSFER
    ),
) -> Transaction:
    return Transaction(
        transaction_type=transaction_type,
        amount=amount,
        currency=currency,
        sender=sender,
        recipient=recipient,
        transaction_id=transaction_id,
        created_at=CURRENT_TIME,
    )


def test_process_internal_transfer() -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "internal",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is True
    assert sender.balance == Decimal("900")
    assert recipient.balance == Decimal("600")
    assert transaction.commission == Decimal("0.00")
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.processed_at == CURRENT_TIME
    assert transaction.attempts == 1
    assert processor.error_log == []


def test_process_external_transfer_with_commission() -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "external",
        sender,
        recipient,
        transaction_type=TransactionType.EXTERNAL_TRANSFER,
    )
    processor = TransactionProcessor(
        external_commission_rate=Decimal("0.01"),
        time_provider=lambda: CURRENT_TIME,
    )

    result = processor.process(transaction)

    assert result is True
    assert transaction.commission == Decimal("1.00")
    assert sender.balance == Decimal("899.00")
    assert recipient.balance == Decimal("600")
    assert transaction.status is TransactionStatus.COMPLETED


def test_process_transfer_with_currency_conversion() -> None:
    sender = create_account(
        "sender-usd",
        Decimal("1000"),
        Currency.USD,
    )
    recipient = create_account(
        "recipient-rub",
        Decimal("500"),
        Currency.RUB,
    )
    transaction = create_transaction(
        "conversion",
        sender,
        recipient,
        amount=Decimal("100"),
        currency=Currency.USD,
    )
    processor = TransactionProcessor(
        conversion_rates={
            (Currency.USD, Currency.RUB): Decimal("80"),
        },
        time_provider=lambda: CURRENT_TIME,
    )

    result = processor.process(transaction)

    assert result is True
    assert sender.balance == Decimal("900")
    assert recipient.balance == Decimal("8500.00")
    assert transaction.status is TransactionStatus.COMPLETED


def test_reject_transfer_without_conversion_rate() -> None:
    sender = create_account(
        "sender-usd",
        Decimal("1000"),
        Currency.USD,
    )
    recipient = create_account(
        "recipient-rub",
        Decimal("500"),
        Currency.RUB,
    )
    transaction = create_transaction(
        "missing-rate",
        sender,
        recipient,
        currency=Currency.USD,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is False
    assert sender.balance == Decimal("1000")
    assert recipient.balance == Decimal("500")
    assert transaction.status is TransactionStatus.FAILED
    assert "курс конвертации" in transaction.failure_reason
    assert transaction.attempts == 1
    assert len(processor.error_log) == 1


def test_reject_transfer_from_frozen_account() -> None:
    sender = create_account(
        "frozen-sender",
        Decimal("1000"),
        status=AccountStatus.FROZEN,
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "frozen-sender-transfer",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is False
    assert sender.balance == Decimal("1000")
    assert recipient.balance == Decimal("500")
    assert transaction.status is TransactionStatus.FAILED
    assert "заморожен" in transaction.failure_reason


def test_reject_transfer_to_frozen_account() -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "frozen-recipient",
        Decimal("500"),
        status=AccountStatus.FROZEN,
    )
    transaction = create_transaction(
        "frozen-recipient-transfer",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is False
    assert sender.balance == Decimal("1000")
    assert recipient.balance == Decimal("500")
    assert transaction.status is TransactionStatus.FAILED


def test_reject_transfer_with_insufficient_funds() -> None:
    sender = create_account(
        "sender",
        Decimal("50"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "insufficient",
        sender,
        recipient,
        amount=Decimal("100"),
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is False
    assert sender.balance == Decimal("50")
    assert recipient.balance == Decimal("500")
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.attempts == 1


def test_allow_premium_account_overdraft() -> None:
    sender = PremiumAccount(
        owner="Премиальный клиент",
        balance=Decimal("100"),
        currency=Currency.RUB,
        withdrawal_limit=Decimal("10000"),
        overdraft_limit=Decimal("1000"),
        fixed_commission=Decimal("10"),
        account_id="premium-sender",
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = Transaction(
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("500"),
        currency=Currency.RUB,
        sender=sender,
        recipient=recipient,
        transaction_id="premium-overdraft",
        created_at=CURRENT_TIME,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    result = processor.process(transaction)

    assert result is True
    assert sender.balance == Decimal("-410")
    assert recipient.balance == Decimal("1000")
    assert transaction.status is TransactionStatus.COMPLETED


def test_repeat_transaction_after_temporary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "retry-success",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        max_retries=1,
        time_provider=lambda: CURRENT_TIME,
    )
    original_withdraw = sender.withdraw
    call_count = 0

    def unstable_withdraw(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            raise RuntimeError("Временная ошибка.")

        return original_withdraw(amount)

    monkeypatch.setattr(sender, "withdraw", unstable_withdraw)

    result = processor.process(transaction)

    assert result is True
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 2
    assert sender.balance == Decimal("900")
    assert recipient.balance == Decimal("600")
    assert len(processor.error_log) == 1
    assert processor.error_log[0]["error"] == "Временная ошибка."


def test_rollback_balances_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "recipient-retry",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        max_retries=1,
        time_provider=lambda: CURRENT_TIME,
    )
    original_deposit = recipient.deposit
    call_count = 0

    def unstable_deposit(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        nonlocal call_count
        call_count += 1
        result = original_deposit(amount)

        if call_count == 1:
            raise RuntimeError("Временная ошибка пополнения.")

        return result

    monkeypatch.setattr(
        recipient,
        "deposit",
        unstable_deposit,
    )

    result = processor.process(transaction)

    assert result is True
    assert transaction.status is TransactionStatus.COMPLETED
    assert transaction.attempts == 2
    assert sender.balance == Decimal("900")
    assert recipient.balance == Decimal("600")
    assert len(processor.error_log) == 1
    assert processor.error_log[0]["error"] == (
        "Временная ошибка пополнения."
    )


def test_fail_after_all_retry_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "retry-failed",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        max_retries=2,
        time_provider=lambda: CURRENT_TIME,
    )

    def failing_withdraw(
        amount: Decimal | int | float | str,
    ) -> Decimal:
        raise RuntimeError("Техническая ошибка.")

    monkeypatch.setattr(sender, "withdraw", failing_withdraw)

    result = processor.process(transaction)

    assert result is False
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.failure_reason == "Техническая ошибка."
    assert transaction.attempts == 3
    assert sender.balance == Decimal("1000")
    assert recipient.balance == Decimal("500")
    assert len(processor.error_log) == 3


def test_process_all_available_transactions() -> None:
    sender_one = create_account(
        "sender-one",
        Decimal("1000"),
    )
    recipient_one = create_account(
        "recipient-one",
        Decimal("500"),
    )
    sender_two = create_account(
        "sender-two",
        Decimal("1000"),
    )
    recipient_two = create_account(
        "recipient-two",
        Decimal("500"),
    )
    normal = create_transaction(
        "normal",
        sender_one,
        recipient_one,
    )
    high = create_transaction(
        "high",
        sender_two,
        recipient_two,
    )
    queue = TransactionQueue(
        time_provider=lambda: CURRENT_TIME
    )
    queue.add(normal, TransactionPriority.NORMAL)
    queue.add(high, TransactionPriority.HIGH)
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )

    processed = processor.process_all(queue)

    assert processed == [high, normal]
    assert high.status is TransactionStatus.COMPLETED
    assert normal.status is TransactionStatus.COMPLETED
    assert len(queue) == 0


def test_reject_repeated_processing() -> None:
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "completed",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        time_provider=lambda: CURRENT_TIME
    )
    processor.process(transaction)

    with pytest.raises(InvalidOperationError):
        processor.process(transaction)


@pytest.mark.parametrize(
    "commission_rate",
    [
        Decimal("-0.01"),
        Decimal("1.01"),
        True,
        "incorrect",
        Decimal("NaN"),
    ],
)
def test_reject_invalid_commission_rate(
    commission_rate: Decimal | str | bool,
) -> None:
    with pytest.raises(InvalidOperationError):
        TransactionProcessor(
            external_commission_rate=commission_rate
        )


@pytest.mark.parametrize(
    "max_retries",
    [-1, 1.5, True],
)
def test_reject_invalid_max_retries(
    max_retries: int | float | bool,
) -> None:
    with pytest.raises(InvalidOperationError):
        TransactionProcessor(max_retries=max_retries)


def test_reject_night_transfer() -> None:
    night_time = datetime(2026, 9, 27, 2, 0)
    sender = create_account(
        "sender",
        Decimal("1000"),
    )
    recipient = create_account(
        "recipient",
        Decimal("500"),
    )
    transaction = create_transaction(
        "night-transfer",
        sender,
        recipient,
    )
    processor = TransactionProcessor(
        time_provider=lambda: night_time
    )

    result = processor.process(transaction)

    assert result is False
    assert sender.balance == Decimal("1000")
    assert recipient.balance == Decimal("500")
    assert transaction.status is TransactionStatus.FAILED
    assert transaction.failure_reason == (
        "Переводы запрещены с 00:00 до 05:00."
    )
    assert transaction.attempts == 1
    assert len(processor.error_log) == 1
    assert processor.error_log[0]["error"] == (
        "Переводы запрещены с 00:00 до 05:00."
    )
