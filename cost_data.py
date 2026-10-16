"""Unit-cost dataset loader for EcoConstruct AI - Member 4.

Member 2 owns the emission-factor dataset (`data/materials.csv`). Nobody else
owned costs, but the scenario engine has to answer "what does this cost?", so
this module loads a companion cost table (`data/material_costs.csv`).

The rules this module follows, on purpose:

    - A missing cost is reported, never guessed. If a material has no row in
      the cost table the scenario still calculates carbon; the cost total is
      simply flagged as incomplete instead of silently treating the cost as 0.
    - Every cost row carries its own currency and verification status, and
      both are surfaced to the client, because a cost comparison built on
      placeholder prices is a scenario, not a quotation.
    - Costs are never mixed across currencies. A scenario with rows in two
      different currencies is reported as unusable for comparison rather than
      being summed into one meaningless number.

`materials.csv` marks every factor `unverified` and its notes say the values
are illustrative. The cost table carries the same caveat: `verification_status`
is `unverified` for every row and `source_name` is BUSINESS_PLACEHOLDER. The
integration work that is still outstanding is replacing both tables with
cited regional data and real supplier quotations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from paths import COSTS_CSV

# Columns the loader insists on. Mirrors Member 2's REQUIRED_COLUMNS approach
# so both datasets fail in the same way and for the same reason.
REQUIRED_COLUMNS = [
    "material_id",
    "unit",
    "unit_cost",
    "currency",
    "verification_status",
]

# Fallback currency used when a cost row does not name one. Keeping it explicit
# means "missing currency" never silently becomes "zero currency".
DEFAULT_CURRENCY = "INR"


class CostDataError(ValueError):
    """The cost dataset is missing, malformed, or internally inconsistent.

    This is a ValueError so the HTTP layer can catch it with the same handler
    it already uses for Member 2's dataset errors.
    """


@dataclass
class UnitCost:
    """One row of the cost table: what one `unit` of a material costs."""

    material_id: str
    unit: str
    unit_cost: float
    currency: str
    cost_basis: str
    source_name: str
    verification_status: str

    def cost_for(self, quantity: float) -> float:
        """Cost of `quantity` units. Linear, because the table is per unit."""
        return quantity * self.unit_cost


class CostData:
    """Loads and serves unit costs keyed by material_id.

    Usage:
        costs = CostData()                       # default path
        costs = CostData("data/my_costs.csv")     # explicit path
        costs.unit_cost_for("MAT002")             # -> UnitCost or None
    """

    def __init__(self, dataset_path: Optional[str] = None) -> None:
        """
        Args:
            dataset_path: Path to the cost CSV. When None, resolves to
                `<project root>/data/material_costs.csv`, i.e. the sibling of
                Member 2's `data/materials.csv`.
        """
        if dataset_path is None:
            dataset_path = COSTS_CSV

        self.dataset_path = dataset_path
        self.costs_df: Optional[pd.DataFrame] = None
        self._by_id: Dict[str, UnitCost] = {}
        self._load_dataset()

    # ------------------------------------------------------------------
    # Loading and validation
    # ------------------------------------------------------------------

    def _load_dataset(self) -> None:
        if not os.path.exists(self.dataset_path):
            raise CostDataError(f"Cost dataset file not found: {self.dataset_path}")

        try:
            self.costs_df = pd.read_csv(self.dataset_path)
        except Exception as exc:  # noqa: BLE001 - surfaced as a CostDataError
            raise CostDataError(f"Failed to read cost CSV file: {exc}") from exc

        self._validate_dataset()
        self._index_rows()

    def _validate_dataset(self) -> None:
        if self.costs_df is None:
            raise CostDataError("Cost dataset not loaded")

        missing = [
            col for col in REQUIRED_COLUMNS if col not in self.costs_df.columns
        ]
        if missing:
            raise CostDataError(f"Missing required columns: {missing}")

        if self.costs_df["material_id"].duplicated().any():
            duplicates = self.costs_df[
                self.costs_df["material_id"].duplicated()
            ]["material_id"].tolist()
            raise CostDataError(f"Duplicate material IDs in cost table: {duplicates}")

        if not pd.api.types.is_numeric_dtype(self.costs_df["unit_cost"]):
            raise CostDataError("unit_cost column must be numeric")

        if (self.costs_df["unit_cost"] < 0).any():
            invalid = self.costs_df[self.costs_df["unit_cost"] < 0][
                "material_id"
            ].tolist()
            raise CostDataError(f"Negative unit costs found for: {invalid}")

        blank_currency = self.costs_df[
            self.costs_df["currency"].isna() | (self.costs_df["currency"] == "")
        ]["material_id"].tolist()
        if blank_currency:
            raise CostDataError(f"Missing currency for: {blank_currency}")

    def _index_rows(self) -> None:
        assert self.costs_df is not None  # guarded by _load_dataset
        for _, row in self.costs_df.iterrows():
            currency = str(row["currency"]).strip() or DEFAULT_CURRENCY
            self._by_id[str(row["material_id"])] = UnitCost(
                material_id=str(row["material_id"]),
                unit=str(row["unit"]),
                unit_cost=float(row["unit_cost"]),
                currency=currency,
                cost_basis=str(row.get("cost_basis", "")),
                source_name=str(row.get("source_name", "")),
                verification_status=str(row["verification_status"]),
            )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def unit_cost_for(self, material_id: str) -> Optional[UnitCost]:
        """Return the UnitCost for `material_id`, or None when it has no row.

        None is a real, expected answer: it means "this material has no price
        in the cost table", which the caller must report rather than guess.
        """
        return self._by_id.get(material_id)

    def currency_for(self, material_ids: List[str]) -> Optional[str]:
        """The single currency shared by `material_ids`, or None.

        Returns None when the list is empty, when any material has no cost
        row, or when the materials are priced in more than one currency - all
        three of which mean "do not present this as one cost total".
        """
        currencies = set()
        for material_id in material_ids:
            unit_cost = self.unit_cost_for(material_id)
            if unit_cost is None:
                return None
            currencies.add(unit_cost.currency)

        if len(currencies) != 1:
            return None
        return currencies.pop()

    def all_costs(self) -> List[UnitCost]:
        """Every row in the table, ordered by material_id."""
        return [self._by_id[key] for key in sorted(self._by_id)]

    def costs_are_verified(self) -> bool:
        """True only when every price in the table is marked verified.

        The dashboard uses this to label cost figures as indicative while the
        table is still placeholder data.
        """
        return all(
            cost.verification_status == "verified" for cost in self._by_id.values()
        )


def create_cost_data(dataset_path: Optional[str] = None) -> CostData:
    """Factory for CostData, mirroring Member 2's create_calculator()."""
    return CostData(dataset_path)
