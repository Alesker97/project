from decimal import Decimal

from src.accounts.bank_account import BankAccount
from src.enums.account_status import AccountStatus
from src.enums.asset_type import AssetType
from src.enums.currency import Currency
from src.exceptions import InsufficientFundsError, InvalidOperationError


class InvestmentAccount(BankAccount):
    def __init__(
        self,
        owner: str,
        balance: Decimal | int | float = 0,
        currency: Currency = Currency.RUB,
        status: AccountStatus = AccountStatus.ACTIVE,
        account_id: str | None = None,
    ) -> None:
        super().__init__(
            owner=owner,
            balance=balance,
            currency=currency,
            status=status,
            account_id=account_id,
        )
        self._portfolio = {
            asset_type: Decimal("0")
            for asset_type in AssetType
        }

    @property
    def portfolio(self) -> dict[AssetType, Decimal]:
        return self._portfolio.copy()

    @property
    def portfolio_value(self) -> Decimal:
        return sum(self._portfolio.values(), Decimal("0"))

    @staticmethod
    def _validate_asset_type(asset_type: AssetType) -> AssetType:
        if not isinstance(asset_type, AssetType):
            raise InvalidOperationError(
                "Передан неподдерживаемый тип актива."
            )

        return asset_type

    def invest(
        self,
        asset_type: AssetType,
        amount: Decimal | int | float,
    ) -> Decimal:
        validated_asset_type = self._validate_asset_type(asset_type)
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()

        if decimal_amount > self._balance:
            raise InsufficientFundsError(
                "Недостаточно свободных средств для инвестиции."
            )

        self._balance -= decimal_amount
        self._portfolio[validated_asset_type] += decimal_amount

        return self._portfolio[validated_asset_type]

    def withdraw(
        self,
        amount: Decimal | int | float,
    ) -> Decimal:
        decimal_amount = self._validate_amount(amount)
        self._ensure_operations_allowed()

        if decimal_amount > self._balance:
            raise InsufficientFundsError(
                "Недостаточно свободных средств для снятия."
            )

        self._balance -= decimal_amount

        return self._balance

    def project_yearly_growth(
        self,
        growth_rates: dict[
            AssetType,
            Decimal | int | float,
        ],
    ) -> Decimal:
        if not isinstance(growth_rates, dict):
            raise InvalidOperationError(
                "Ставки доходности должны быть переданы словарём."
            )

        if set(growth_rates) != set(AssetType):
            raise InvalidOperationError(
                "Ставки должны быть указаны для всех типов активов."
            )

        projected_growth = Decimal("0")

        for asset_type, amount in self._portfolio.items():
            try:
                growth_rate = self._convert_to_decimal(
                    growth_rates[asset_type]
                )
            except InvalidOperationError as error:
                raise InvalidOperationError(
                    "Годовая ставка должна быть конечным числом."
                ) from error

            projected_growth += amount * growth_rate

        return projected_growth

    def get_account_info(self) -> dict[str, object]:
        account_info = super().get_account_info()
        account_info.update(
            {
                "portfolio": {
                    asset_type.value: f"{amount:.2f}"
                    for asset_type, amount in self._portfolio.items()
                },
                "portfolio_value": f"{self.portfolio_value:.2f}",
            }
        )

        return account_info

    def __str__(self) -> str:
        portfolio_details = ", ".join(
            f"{asset_type.value}={amount:.2f}"
            for asset_type, amount in self._portfolio.items()
        )

        return (
            f"{super().__str__()} | "
            f"Портфель: {portfolio_details} "
            f"{self._currency.value} | "
            f"Стоимость портфеля: {self.portfolio_value:.2f} "
            f"{self._currency.value}"
        )
