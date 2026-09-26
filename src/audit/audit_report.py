from src.audit.audit_log import AuditLog
from src.enums.audit_level import AuditLevel
from src.enums.risk_level import RiskLevel
from src.exceptions import InvalidOperationError


class AuditReport:
    def __init__(self, audit_log: AuditLog) -> None:
        if not isinstance(audit_log, AuditLog):
            raise InvalidOperationError(
                "Передан некорректный журнал аудита."
            )
        self._audit_log = audit_log

    def get_suspicious_operations(
        self,
    ) -> list[dict[str, object]]:
        risk_entries = self._audit_log.filter(
            event_type="risk_assessment"
        )
        suspicious_entries = []

        for entry in risk_entries:
            risk_level = self._extract_risk_level(entry)

            if risk_level in (
                RiskLevel.MEDIUM,
                RiskLevel.HIGH,
            ):
                suspicious_entries.append(entry)

        return suspicious_entries

    def get_client_risk_profile(
        self,
        client_id: str,
    ) -> dict[str, object]:
        client_id = self._validate_client_id(client_id)
        risk_entries = self._audit_log.filter(
            event_type="risk_assessment",
            client_id=client_id,
        )
        risk_counts = {
            risk_level.value: 0
            for risk_level in RiskLevel
        }
        detected_levels = []

        for entry in risk_entries:
            risk_level = self._extract_risk_level(entry)

            if risk_level is not None:
                risk_counts[risk_level.value] += 1
                detected_levels.append(risk_level)

        blocked_operations = self._audit_log.filter(
            event_type="transaction_blocked",
            client_id=client_id,
        )

        return {
            "client_id": client_id,
            "total_operations": sum(risk_counts.values()),
            "risk_counts": risk_counts,
            "blocked_operations": len(blocked_operations),
            "maximum_risk": self._get_maximum_risk(
                detected_levels
            ),
        }

    def get_error_statistics(self) -> dict[str, object]:
        error_entries = self._audit_log.filter(
            level=AuditLevel.ERROR
        )
        critical_entries = self._audit_log.filter(
            level=AuditLevel.CRITICAL
        )
        entries = error_entries + critical_entries
        by_event_type: dict[str, int] = {}

        for entry in entries:
            event_type = entry["event_type"]

            if isinstance(event_type, str):
                by_event_type[event_type] = (
                    by_event_type.get(event_type, 0) + 1
                )

        return {
            "total_errors": len(entries),
            "by_event_type": by_event_type,
        }

    @staticmethod
    def _extract_risk_level(
        entry: dict[str, object],
    ) -> RiskLevel | None:
        details = entry.get("details")

        if not isinstance(details, dict):
            return None

        risk_value = details.get("risk_level")

        if isinstance(risk_value, RiskLevel):
            return risk_value

        if isinstance(risk_value, str):
            try:
                return RiskLevel(risk_value)
            except ValueError:
                return None

        return None

    @staticmethod
    def _get_maximum_risk(
        risk_levels: list[RiskLevel],
    ) -> RiskLevel | None:
        if not risk_levels:
            return None

        risk_order = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        return max(
            risk_levels,
            key=risk_order.__getitem__,
        )

    @staticmethod
    def _validate_client_id(client_id: str) -> str:
        if not isinstance(client_id, str) or not client_id.strip():
            raise InvalidOperationError(
                "ID клиента указан некорректно."
            )
        return client_id.strip()
