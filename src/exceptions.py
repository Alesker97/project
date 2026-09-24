class BankingError(Exception):
    pass


class AccountFrozenError(BankingError):
    pass


class AccountClosedError(BankingError):
    pass


class InvalidOperationError(BankingError):
    pass


class InsufficientFundsError(BankingError):
    pass
