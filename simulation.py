"""Scenario-based construction lifecycle simulation for EcoConstruct AI - Member 4.

The "digital twin" in this project is deliberately a scenario model, not a 3D
replica of a site: a Scenario is a bill of quantities (material_id + quantity
per line), and the twin evaluates that bill through the *same* carbon engine
Member 2 owns. Two scenarios - a baseline and an alternative - are then
compared on carbon and cost.

The integration rule this module exists to enforce:

    Member 2 owns the carbon calculation logic.
    Member 4 reuses it for every scenario, so the dashboard, the AI
    assistant and the simulator can never disagree about a number.

Concretely, emissions come from `backend.carbon_calculator.py`. This module
adds no emission factor of its own, and `MaterialLine.emissions_kg_co2e` is
read straight out of Member 2's `ProjectTotal`. What this module adds on top
is cost, and the delta between two scenarios.

What this module will not do:

    - Invent a cost for a material that has no row in the cost table. Such a
      line contributes carbon but no cost, and the result is flagged
      `cost_is_complete = False` so the UI can say "cost excludes X".
    - Present a percentage reduction against a zero baseline. A 0 kg CO2e
      baseline yields `percentage_reduction = 0.0` with a warning, because
      "infinitely many percent saved" is not a useful number for a manager.
    - Mix currencies. A comparison spanning two currencies is rejected.

Two worked examples are in `DEMO_SCENARIOS` at the bottom of this file; run
`python simulation.py` to print them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from backend.carbon_calculator import CarbonCalculator, create_calculator
from cost_data import CostData, UnitCost, create_cost_data

# Every emission factor in data/materials.csv is currently marked unverified,
# and Member 2's CarbonCalculator refuses unverified factors unless it is told
# to allow them. For a prototype whose dataset is explicitly illustrative, the
# simulation allows them and then says so in `warnings` on every result, so a
# reviewer is never misled into thinking these are certified factors.
ALLOW_UNVERIFIED_FACTORS = True

KG_PER_TONNE = 1000.0


class ScenarioError(ValueError):
    """A scenario is empty, malformed, or cannot be compared as requested."""


# --------------------------------------------------------------------------
# Input models
# --------------------------------------------------------------------------


@dataclass
class ScenarioItem:
    """One line of a bill of quantities.

    Attributes:
        material_id: Must exist in Member 2's dataset.
        quantity: In the material's own dataset unit (kg, tonne, m3, liter,
                  or brick "unit"). Zero and negative quantities are rejected
                  by the engine.
        note: Optional free text, e.g. "50 m3 of the podium slab".
    """

    material_id: str
    quantity: float
    note: str = ""


@dataclass
class Scenario:
    """A named construction scenario: a baseline, or a proposed alternative.

    `floor_area_m2` is optional and exists so the dashboard can report carbon
    intensity (kg CO2e per m2 of built area) - the metric a construction team
    is actually measured on. Without it, intensity is reported as None rather
    than against an invented denominator.
    """

    name: str
    items: List[ScenarioItem]
    description: str = ""
    floor_area_m2: Optional[float] = None

    def aggregated_quantities(self) -> Dict[str, float]:
        """Sum quantities per material_id, dropping zero and negative lines.

        Member 2's calculate_project_total() keys its result dict by
        material_id, so two lines for the same material would silently keep
        only the first. Aggregating first makes the sum explicit and keeps
        Member 2's engine from losing a line.
        """
        totals: Dict[str, float] = {}
        for item in self.items:
            quantity = float(item.quantity)
            if quantity <= 0:
                continue
            totals[item.material_id] = totals.get(item.material_id, 0.0) + quantity
        return totals


# --------------------------------------------------------------------------
# Output models
# --------------------------------------------------------------------------


@dataclass
class MaterialLine:
    """One evaluated line of a scenario, with its carbon and its cost."""

    material_id: str
    material_name: str
    category: str
    quantity: float
    unit: str
    emission_factor: float
    factor_unit: str
    emissions_kg_co2e: float
    share_of_total_percent: float = 0.0
    unit_cost: Optional[float] = None
    currency: Optional[str] = None
    cost_total: Optional[float] = None
    cost_verification_status: Optional[str] = None
    factor_verification_status: Optional[str] = None

    @property
    def has_cost(self) -> bool:
        return self.cost_total is not None


@dataclass
class ScenarioResult:
    """A scenario evaluated into totals, per-line detail and per-category rollups."""

    scenario_name: str
    description: str
    total_emissions_kg_co2e: float
    total_emissions_tonnes_co2e: float
    total_cost: float
    currency: Optional[str]
    cost_is_complete: bool
    lines: List[MaterialLine] = field(default_factory=list)
    emissions_by_category: Dict[str, float] = field(default_factory=dict)
    cost_by_category: Dict[str, float] = field(default_factory=dict)
    hotspot_material_id: Optional[str] = None
    hotspot_material_name: Optional[str] = None
    hotspot_share_percent: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def top_lines(self, count: int = 5) -> List[MaterialLine]:
        """The `count` largest lines by emissions, biggest first."""
        return sorted(
            self.lines, key=lambda line: line.emissions_kg_co2e, reverse=True
        )[:count]

    def line_for(self, material_id: str) -> Optional[MaterialLine]:
        for line in self.lines:
            if line.material_id == material_id:
                return line
        return None


@dataclass
class MaterialDelta:
    """How one material changed between the baseline and the alternative.

    Sign convention for this dataclass: every `*_delta` field is
    **alternative minus baseline**. A positive value therefore means the
    alternative is *worse* for that material (more carbon, more money). Read
    them as "the change this material contributed to", not as a saving.

    (The project-level `emissions_reduction_*` and `cost_saving*` fields on
    ScenarioComparison use the opposite, benefit-positive convention, because
    they are reductions and savings. Each is documented on that class.)

    `change_type` is one of:
        substituted  - a different material was used
        unchanged    - same material, same quantity
        increased    - same material, more of it
        reduced      - same material, less of it
        removed      - in the baseline only
        added        - in the alternative only
    """

    material_id: str
    material_name: str
    change_type: str
    baseline_quantity: float
    alternative_quantity: float
    baseline_emissions_kg_co2e: float
    alternative_emissions_kg_co2e: float
    emissions_delta_kg_co2e: float
    cost_delta: Optional[float]
    unit: str
    # Set only for change_type="substituted": what it was swapped for.
    alternative_material_id: Optional[str] = None
    alternative_material_name: Optional[str] = None


@dataclass
class ScenarioComparison:
    """Baseline vs alternative, on carbon and on cost.

    Sign convention for this class, stated once so the UI cannot misread it:

        A positive `emissions_reduction_*`  -> the alternative emits LESS.
        A positive `cost_saving`            -> the alternative COSTS LESS.
        A positive `cost_saving_percent`    -> ditto, as a share of baseline.
        A positive `cost_per_tonne_avoided` -> the alternative is both
                                               cheaper and lower-carbon, by
                                               this much per tonne avoided.

    `cost_saving` and `cost_per_tonne_avoided` are `0.0` and `None`
    respectively when the cost comparison is not usable (a missing price, or
    two currencies), which is why `cost_is_complete` is exposed alongside
    them and why the reason is always pushed onto `warnings`.
    """

    baseline: ScenarioResult
    alternative: ScenarioResult
    emissions_baseline_kg_co2e: float
    emissions_alternative_kg_co2e: float
    emissions_reduction_kg_co2e: float
    emissions_reduction_tonnes_co2e: float
    emissions_reduction_percent: float
    cost_baseline: float
    cost_alternative: float
    cost_saving: float
    cost_saving_percent: float
    currency: Optional[str]
    cost_is_complete: bool
    cost_per_tonne_avoided: Optional[float]
    material_deltas: List[MaterialDelta] = field(default_factory=list)
    changed_material_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


class SimulationEngine:
    """Evaluates scenarios and compares them.

    Usage:
        engine = SimulationEngine()
        result = engine.evaluate(Scenario("baseline", [ScenarioItem("MAT002", 500)]))
        comparison = engine.compare(baseline_scenario, alternative_scenario)
    """

    def __init__(
        self,
        calculator: Optional[CarbonCalculator] = None,
        costs: Optional[CostData] = None,
        allow_unverified: bool = ALLOW_UNVERIFIED_FACTORS,
    ) -> None:
        """
        Args:
            calculator: Member 2's engine. One is created from the default
                        dataset when omitted.
            costs: The cost table. One is created from the default dataset
                   when omitted.
            allow_unverified: Whether unverified emission factors may be used.
                             The default is True because every factor in the
                             current dataset is unverified; results always
                             carry a warning saying so.
        """
        self.calculator = calculator or create_calculator()
        self.costs = costs or create_cost_data()
        self.allow_unverified = allow_unverified

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, scenario: Scenario) -> ScenarioResult:
        """Run one scenario through Member 2's engine and add cost on top.

        Raises:
            ScenarioError: if the scenario has no usable lines, or if a
                material_id is not in Member 2's dataset.
        """
        quantities = scenario.aggregated_quantities()
        if not quantities:
            raise ScenarioError(
                f"Scenario '{scenario.name}' has no material lines with a "
                "quantity greater than zero."
            )

        # Unknown material IDs are rejected here, with a message naming the
        # bad ID, rather than as a bare KeyError from deep inside the engine.
        for material_id in quantities:
            try:
                self.calculator.get_material(
                    material_id, allow_unverified=self.allow_unverified
                )
            except ValueError as exc:
                raise ScenarioError(
                    f"Scenario '{scenario.name}' references an unknown "
                    f"material '{material_id}': {exc}"
                ) from exc

        warnings: List[str] = []

        # --- Carbon: delegated entirely to Member 2's engine --------------
        # MaterialEmission.emissions_kg_co2e below comes from this call, not
        # from any arithmetic in this module.
        project_total = self.calculator.calculate_project_total(
            [{"material_id": mid, "quantity": qty} for mid, qty in quantities.items()],
            allow_unverified=self.allow_unverified,
        )

        total_emissions = float(project_total.total_emissions_kg_co2e)

        lines: List[MaterialLine] = []
        total_cost = 0.0
        missing_cost: List[str] = []
        currencies = set()
        unverified_factors: List[str] = []

        for material_id, quantity in quantities.items():
            row = self.calculator.get_material(
                material_id, allow_unverified=self.allow_unverified
            )
            emission = project_total.emissions_by_material[material_id]

            if str(row["verification_status"]) != "verified":
                unverified_factors.append(material_id)

            unit_cost = self.costs.unit_cost_for(material_id)
            line = MaterialLine(
                material_id=material_id,
                material_name=str(row["material_name"]),
                category=str(row["category"]),
                quantity=quantity,
                unit=str(row["unit"]),
                emission_factor=float(emission.emission_factor),
                factor_unit=str(emission.factor_unit),
                emissions_kg_co2e=float(emission.emissions_kg_co2e),
                share_of_total_percent=(
                    float(emission.emissions_kg_co2e) / total_emissions * 100
                    if total_emissions > 0
                    else 0.0
                ),
                factor_verification_status=str(row["verification_status"]),
            )

            if unit_cost is None:
                # No price on file. Carbon still counts; cost does not, and the
                # gap is reported rather than absorbed as a silent zero.
                missing_cost.append(material_id)
                line.cost_verification_status = None
            else:
                self._attach_cost(line, unit_cost, quantity)
                total_cost += line.cost_total or 0.0
                currencies.add(unit_cost.currency)

            lines.append(line)

        lines.sort(key=lambda line: line.emissions_kg_co2e, reverse=True)

        currency = self._single_currency(currencies, missing_cost, scenario.name)
        cost_is_complete = not missing_cost

        # --- Warnings -----------------------------------------------------
        if missing_cost:
            warnings.append(
                "No unit cost on file for: "
                + ", ".join(sorted(missing_cost))
                + ". The cost total excludes these materials and should not be "
                "used for a final commercial decision."
            )
        if currency is None and not missing_cost:
            warnings.append(
                f"Scenario '{scenario.name}' mixes currencies "
                f"({', '.join(sorted(currencies))}); no single cost total is "
                "reported."
            )
        if not self.costs.costs_are_verified():
            warnings.append(
                "All unit costs are unverified placeholders, not supplier "
                "quotations. Carbon and cost figures are indicative only."
            )
        if unverified_factors:
            warnings.append(
                "Emission factors marked unverified in the dataset were used "
                "for: " + ", ".join(sorted(unverified_factors)) + "."
            )
        if total_emissions <= 0:
            warnings.append("Total emissions are zero; shares and percentages are 0.")

        top = lines[0] if lines else None

        return ScenarioResult(
            scenario_name=scenario.name,
            description=scenario.description,
            total_emissions_kg_co2e=total_emissions,
            total_emissions_tonnes_co2e=total_emissions / KG_PER_TONNE,
            total_cost=total_cost,
            currency=currency,
            cost_is_complete=cost_is_complete,
            lines=lines,
            emissions_by_category=dict(project_total.emissions_by_category),
            cost_by_category=self._cost_by_category(lines),
            hotspot_material_id=top.material_id if top else None,
            hotspot_material_name=top.material_name if top else None,
            hotspot_share_percent=top.share_of_total_percent if top else 0.0,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(
        self, baseline: Scenario, alternative: Scenario
    ) -> ScenarioComparison:
        """Evaluate both scenarios and quantify the difference.

        Raises:
            ScenarioError: if either scenario cannot be evaluated.
        """
        baseline_result = self.evaluate(baseline)
        alternative_result = self.evaluate(alternative)

        return self.compare_results(baseline_result, alternative_result)

    def compare_results(
        self, baseline: ScenarioResult, alternative: ScenarioResult
    ) -> ScenarioComparison:
        """Compare two already-evaluated scenarios."""
        warnings: List[str] = list(baseline.warnings) + list(alternative.warnings)

        base_emissions = baseline.total_emissions_kg_co2e
        alt_emissions = alternative.total_emissions_kg_co2e

        # Positive reduction means the alternative is better.
        reduction_kg = base_emissions - alt_emissions
        reduction_tonnes = reduction_kg / KG_PER_TONNE

        if base_emissions > 0:
            reduction_percent = reduction_kg / base_emissions * 100
        else:
            reduction_percent = 0.0
            warnings.append(
                "Baseline emissions are zero, so a percentage reduction cannot "
                "be calculated and is reported as 0."
            )

        cost_complete = baseline.cost_is_complete and alternative.cost_is_complete
        currency = (
            baseline.currency
            if baseline.currency == alternative.currency
            else None
        )
        if currency is None and cost_complete:
            warnings.append(
                "Baseline and alternative costs are in different currencies; "
                "the cost difference is reported as unavailable."
            )

        # --- Cost saving ---------------------------------------------------
        # Positive saving means the alternative is cheaper than the baseline.
        if cost_complete and currency is not None:
            cost_baseline = baseline.total_cost
            cost_alternative = alternative.total_cost
            cost_saving = cost_baseline - cost_alternative
            if cost_baseline > 0:
                cost_saving_percent = cost_saving / cost_baseline * 100
            else:
                cost_saving_percent = 0.0
                warnings.append(
                    "Baseline cost is zero, so a cost percentage saving cannot "
                    "be calculated and is reported as 0."
                )
            if reduction_tonnes > 0:
                cost_per_tonne_avoided = cost_saving / reduction_tonnes
            else:
                cost_per_tonne_avoided = None
                if reduction_kg < 0:
                    warnings.append(
                        "The alternative increases emissions, so a cost per "
                        "tonne avoided is not meaningful and is left empty."
                    )
        else:
            cost_baseline = baseline.total_cost
            cost_alternative = alternative.total_cost
            cost_saving = 0.0
            cost_saving_percent = 0.0
            cost_per_tonne_avoided = None
            if not cost_complete:
                warnings.append(
                    "Cost comparison is incomplete: at least one scenario has "
                    "materials with no unit cost on file. Totals below exclude "
                    "them."
                )

        # A negative saving is the case worth flagging: the manager gets a
        # cleaner project but has to pay more for it.
        if reduction_kg > 0 and cost_saving < 0:
            warnings.append(
                "The alternative reduces emissions but costs more. Report both "
                "figures together rather than as a single verdict."
            )
        elif reduction_kg < 0 and cost_saving > 0:
            warnings.append(
                "The alternative is cheaper but increases emissions."
            )
        elif reduction_kg < 0:
            warnings.append(
                "The alternative increases emissions relative to the baseline."
            )

        deltas, changed_ids = self._material_deltas(baseline, alternative)

        # Both scenarios flag the same dataset caveats, so de-duplicate while
        # preserving order: the client should see each warning once.
        warnings = list(dict.fromkeys(warnings))

        return ScenarioComparison(
            baseline=baseline,
            alternative=alternative,
            emissions_baseline_kg_co2e=base_emissions,
            emissions_alternative_kg_co2e=alt_emissions,
            emissions_reduction_kg_co2e=reduction_kg,
            emissions_reduction_tonnes_co2e=reduction_tonnes,
            emissions_reduction_percent=reduction_percent,
            cost_baseline=cost_baseline,
            cost_alternative=cost_alternative,
            cost_saving=cost_saving,
            cost_saving_percent=cost_saving_percent,
            currency=currency,
            cost_is_complete=cost_complete,
            cost_per_tonne_avoided=cost_per_tonne_avoided,
            material_deltas=deltas,
            changed_material_ids=changed_ids,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Scenario building helpers
    # ------------------------------------------------------------------

    def build_alternative(
        self,
        baseline: Scenario,
        substitutions: Optional[Dict[str, str]] = None,
        quantity_changes: Optional[Dict[str, float]] = None,
        name: str = "alternative",
        description: str = "",
    ) -> Scenario:
        """Derive a what-if scenario from a baseline.

        Args:
            substitutions: `{from_material_id: to_material_id}`. The quantity
                carries over unchanged, which is only physically meaningful
                for materials sharing a unit - compare_materials() enforces
                the same rule, and evaluate() will surface the mismatch in the
                per-line units.
            quantity_changes: `{material_id: new_quantity}` applied after
                substitution, so a substitution and a quantity change can be
                combined for one material.
            name: Name for the derived scenario.
            description: Free text carried into the result.
        """
        substitutions = substitutions or {}
        quantity_changes = quantity_changes or {}

        items: List[ScenarioItem] = []
        for original in baseline.items:
            material_id = substitutions.get(original.material_id, original.material_id)
            quantity = float(quantity_changes.get(material_id, original.quantity))
            items.append(
                ScenarioItem(
                    material_id=material_id,
                    quantity=quantity,
                    note=original.note,
                )
            )

        # Quantity changes for materials the baseline never listed: a genuine
        # "add something new to the design" move, so include them.
        for material_id, quantity in quantity_changes.items():
            if material_id not in {item.material_id for item in baseline.items}:
                if material_id not in substitutions.values():
                    items.append(ScenarioItem(material_id=material_id, quantity=quantity))

        return Scenario(
            name=name,
            items=items,
            description=description
            or (
                "Derived from "
                f"'{baseline.name}' with "
                f"{len(substitutions)} substitution(s) and "
                f"{len(quantity_changes)} quantity change(s)."
            ),
        )

    def suggest_substitutions(self) -> List[Dict[str, str]]:
        """Lower-emission alternatives already present in Member 2's dataset.

        Derived from the data, not from a hard-coded list: for every pair of
        materials in the same category and with the same unit, the one with the
        lower emission factor is a candidate substitution for the higher one.
        Only pairs with a real reduction are returned.
        """
        materials = self.calculator.get_all_materials(verified_only=False)
        rows = materials.to_dict("records")

        candidates: List[Dict[str, str]] = []
        for i, current in enumerate(rows):
            for other in rows[i + 1 :]:
                if current["category"] != other["category"]:
                    continue
                if current["unit"] != other["unit"]:
                    continue
                if current["material_id"] == other["material_id"]:
                    continue

                higher, lower = (
                    (current, other)
                    if float(current["emission_factor"]) > float(other["emission_factor"])
                    else (other, current)
                )
                candidates.append(
                    {
                        "baseline_material_id": str(higher["material_id"]),
                        "baseline_material_name": str(higher["material_name"]),
                        "baseline_variant": str(higher.get("material_variant", "")),
                        "alternative_material_id": str(lower["material_id"]),
                        "alternative_material_name": str(lower["material_name"]),
                        "alternative_variant": str(lower.get("material_variant", "")),
                        "baseline_factor": float(higher["emission_factor"]),
                        "alternative_factor": float(lower["emission_factor"]),
                        "factor_reduction_percent": round(
                            (float(higher["emission_factor"]) - float(lower["emission_factor"]))
                            / float(higher["emission_factor"])
                            * 100,
                            2,
                        ),
                    }
                )

        candidates.sort(key=lambda row: row["factor_reduction_percent"], reverse=True)
        return candidates

    def project_opportunities(
        self, result: ScenarioResult, limit: int = 5
    ) -> List[Dict[str, object]]:
        """Rank the substitutions that would actually move *this* scenario.

        suggest_substitutions() ranks every like-for-like pair in the dataset.
        This narrows that to the materials the evaluated scenario really uses
        and scales each candidate by the quantity in the scenario, so the
        number shown is the project's own t CO2e, not a generic factor ratio.

        Returns:
            One dict per candidate, biggest carbon reduction first. Each carries
            `cost_saving`, which is None when either material has no price on
            file - the carbon case is still shown, with cost reported as
            unknown rather than as zero.
        """
        best_alternative: Dict[str, Dict[str, str]] = {}
        for candidate in self.suggest_substitutions():
            # suggest_substitutions() is already sorted by reduction, so the
            # first entry seen for a material is its best alternative.
            best_alternative.setdefault(
                candidate["baseline_material_id"], candidate
            )

        opportunities: List[Dict[str, object]] = []
        for line in result.lines:
            candidate = best_alternative.get(line.material_id)
            if candidate is None:
                continue

            factor_gap = float(candidate["baseline_factor"]) - float(
                candidate["alternative_factor"]
            )
            reduction_kg = line.quantity * factor_gap
            if reduction_kg <= 0:
                continue

            base_cost = self.costs.unit_cost_for(line.material_id)
            alt_cost = self.costs.unit_cost_for(
                str(candidate["alternative_material_id"])
            )
            cost_saving: Optional[float] = None
            if (
                base_cost is not None
                and alt_cost is not None
                and base_cost.currency == alt_cost.currency
            ):
                cost_saving = base_cost.cost_for(line.quantity) - alt_cost.cost_for(
                    line.quantity
                )

            opportunities.append(
                {
                    "material_id": line.material_id,
                    "material_name": line.material_name,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "current_emissions_kg_co2e": line.emissions_kg_co2e,
                    "alternative_material_id": candidate[
                        "alternative_material_id"
                    ],
                    "alternative_material_name": candidate[
                        "alternative_material_name"
                    ],
                    "alternative_variant": candidate["alternative_variant"],
                    "emissions_reduction_kg_co2e": reduction_kg,
                    "emissions_reduction_tonnes_co2e": reduction_kg / KG_PER_TONNE,
                    "emissions_reduction_percent_of_material": (
                        reduction_kg / line.emissions_kg_co2e * 100
                        if line.emissions_kg_co2e > 0
                        else 0.0
                    ),
                    "cost_saving": cost_saving,
                    "currency": (
                        base_cost.currency
                        if base_cost is not None
                        and alt_cost is not None
                        and base_cost.currency == alt_cost.currency
                        else None
                    ),
                    "requires_validation": True,
                    "note": (
                        "Indicative only: substituting one material for "
                        "another changes cost, lead time and specification "
                        "compliance. Confirm with the design team and the "
                        "supplier before committing."
                    ),
                }
            )

        opportunities.sort(
            key=lambda row: float(row["emissions_reduction_kg_co2e"]), reverse=True
        )
        return opportunities[:limit]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _attach_cost(
        self, line: MaterialLine, unit_cost: UnitCost, quantity: float
    ) -> None:
        line.unit_cost = unit_cost.unit_cost
        line.currency = unit_cost.currency
        line.cost_total = unit_cost.cost_for(quantity)
        line.cost_verification_status = unit_cost.verification_status

    def _single_currency(
        self, currencies: set, missing_cost: List[str], scenario_name: str
    ) -> Optional[str]:
        if missing_cost:
            return None
        if len(currencies) == 1:
            return currencies.pop()
        return None

    def _cost_by_category(self, lines: Sequence[MaterialLine]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for line in lines:
            if line.cost_total is None:
                continue
            totals[line.category] = totals.get(line.category, 0.0) + line.cost_total
        return totals

    def _material_deltas(
        self, baseline: ScenarioResult, alternative: ScenarioResult
    ) -> Tuple[List[MaterialDelta], List[str]]:
        base_lines = {line.material_id: line for line in baseline.lines}
        alt_lines = {line.material_id: line for line in alternative.lines}

        deltas: List[MaterialDelta] = []
        changed_ids: List[str] = []

        # --- Pair like-for-like substitutions first ----------------------
        # A swap of one material for another would otherwise show up as two
        # unrelated rows ("Concrete removed", "Concrete added"), which reads as
        # noise and hides the actual decision. Pair a removed material with an
        # added one only when the unit and quantity match exactly, and only
        # when the match is unambiguous, so a real add or removal is never
        # mislabelled as a swap.
        substituted_pairs = self._pair_substitutions(base_lines, alt_lines)
        consumed = {mid for pair in substituted_pairs for mid in pair}

        for removed_id, added_id in substituted_pairs:
            base = base_lines[removed_id]
            alt = alt_lines[added_id]
            base_cost = base.cost_total
            alt_cost = alt.cost_total
            deltas.append(
                MaterialDelta(
                    material_id=removed_id,
                    material_name=base.material_name,
                    change_type="substituted",
                    baseline_quantity=base.quantity,
                    alternative_quantity=alt.quantity,
                    baseline_emissions_kg_co2e=base.emissions_kg_co2e,
                    alternative_emissions_kg_co2e=alt.emissions_kg_co2e,
                    emissions_delta_kg_co2e=alt.emissions_kg_co2e
                    - base.emissions_kg_co2e,
                    cost_delta=(
                        (alt_cost - base_cost)
                        if base_cost is not None and alt_cost is not None
                        else None
                    ),
                    unit=base.unit,
                    alternative_material_id=added_id,
                    alternative_material_name=alt.material_name,
                )
            )
            changed_ids.extend([removed_id, added_id])

        # --- Everything else that actually changed -------------------------
        for material_id in sorted(set(base_lines) | set(alt_lines)):
            if material_id in consumed:
                continue

            base = base_lines.get(material_id)
            alt = alt_lines.get(material_id)

            base_qty = base.quantity if base else 0.0
            alt_qty = alt.quantity if alt else 0.0
            base_emissions = base.emissions_kg_co2e if base else 0.0
            alt_emissions = alt.emissions_kg_co2e if alt else 0.0

            if base and alt:
                if abs(base_qty - alt_qty) < 1e-9:
                    change_type = "unchanged"
                elif alt_qty > base_qty:
                    change_type = "increased"
                else:
                    change_type = "reduced"
            elif base:
                change_type = "removed"
            else:
                change_type = "added"

            if change_type == "unchanged":
                continue

            cost_delta: Optional[float] = None
            base_cost = base.cost_total if base else None
            alt_cost = alt.cost_total if alt else None
            if base_cost is not None and alt_cost is not None:
                cost_delta = alt_cost - base_cost
            elif change_type in ("added", "removed"):
                # A material entering or leaving is entirely one-sided.
                cost_delta = (alt_cost or 0.0) - (base_cost or 0.0)

            changed_ids.append(material_id)
            deltas.append(
                MaterialDelta(
                    material_id=material_id,
                    material_name=(alt or base).material_name,
                    change_type=change_type,
                    baseline_quantity=base_qty,
                    alternative_quantity=alt_qty,
                    baseline_emissions_kg_co2e=base_emissions,
                    alternative_emissions_kg_co2e=alt_emissions,
                    emissions_delta_kg_co2e=alt_emissions - base_emissions,
                    cost_delta=cost_delta,
                    unit=(alt or base).unit,
                )
            )

        # Biggest carbon movers first, so the UI can show the top few.
        deltas.sort(key=lambda delta: delta.emissions_delta_kg_co2e)
        return deltas, changed_ids

    @staticmethod
    def _pair_substitutions(
        base_lines: Dict[str, MaterialLine], alt_lines: Dict[str, MaterialLine]
    ) -> List[Tuple[str, str]]:
        """Match removed materials to added ones on identical unit + quantity.

        Returns:
            A list of `(removed_material_id, added_material_id)` pairs. Only
            unambiguous matches are returned: if two removed lines and two
            added lines share the same unit and quantity, none of them are
            paired, because any pairing we picked would be a guess.
        """
        removed = [line for mid, line in base_lines.items() if mid not in alt_lines]
        added = [line for mid, line in alt_lines.items() if mid not in base_lines]

        def key_of(line: MaterialLine) -> Tuple[str, float]:
            return (line.unit, round(line.quantity, 9))

        removed_by_key: Dict[Tuple[str, float], List[str]] = {}
        for line in removed:
            removed_by_key.setdefault(key_of(line), []).append(line.material_id)

        added_by_key: Dict[Tuple[str, float], List[str]] = {}
        for line in added:
            added_by_key.setdefault(key_of(line), []).append(line.material_id)

        pairs: List[Tuple[str, str]] = []
        for key in sorted(set(removed_by_key) & set(added_by_key)):
            removed_ids = sorted(removed_by_key[key])
            added_ids = sorted(added_by_key[key])
            if len(removed_ids) == 1 and len(added_ids) == 1:
                pairs.append((removed_ids[0], added_ids[0]))
        return pairs


# --------------------------------------------------------------------------
# Demo scenarios
# --------------------------------------------------------------------------
#
# The quantities below are an illustrative 12-storey office block, chosen only
# to make the comparison legible in a demo. They are not a bill of quantities
# and the emission factors they are multiplied by are unverified.

DEMO_SCENARIOS = {
    "baseline": Scenario(
        name="Baseline - conventional concrete",
        description="As-designed structural package using C30-37 concrete.",
        items=[
            ScenarioItem("MAT002", 2400, "Podium and basement slabs"),
            ScenarioItem("MAT005", 310000, "Reinforcement to slabs and columns"),
            ScenarioItem("MAT010", 185000, "Roof and primary steel frame"),
            ScenarioItem("MAT006", 210000, "External masonry"),
            ScenarioItem("MAT007", 1650, "Blockwork and screeds"),
            ScenarioItem("MAT009", 24000, "Site plant and delivery fleet"),
        ],
    ),
    "alternative": Scenario(
        name="Alternative - low-carbon mix and recycled steel",
        description=(
            "Same structure, with GGBS-blended concrete in the slabs and "
            "supplier-verified recycled-content reinforcement."
        ),
        items=[
            ScenarioItem("MAT004", 1500, "Podium and basement slabs, GGBS mix"),
            ScenarioItem("MAT002", 900, "Columns and cores remain standard mix"),
            ScenarioItem("MAT005", 248000, "Same design, 20% recycled-content rebar"),
            ScenarioItem("MAT010", 185000, "Roof steel unchanged - pending supplier data"),
            ScenarioItem("MAT006", 210000, "Masonry unchanged - pending EPD"),
            ScenarioItem("MAT007", 1650, "Aggregates unchanged"),
            ScenarioItem("MAT009", 21600, "10% fewer haulage trips"),
        ],
    ),
}


def _demo() -> None:
    """Print the worked comparison. Run with: python simulation.py"""
    engine = SimulationEngine()
    comparison = engine.compare(
        DEMO_SCENARIOS["baseline"], DEMO_SCENARIOS["alternative"]
    )

    def row(label: str, base: float, alt: float, unit: str) -> str:
        delta = base - alt
        pct = f" ({delta / base * 100:+.1f}%)" if base else ""
        return (
            f"  {label:<34}{base:>14,.1f}{alt:>14,.1f}"
            f"{delta:>14,.1f}{unit}{pct}"
        )

    print("=" * 84)
    print("ECOCONSTRUCT AI - SCENARIO SIMULATION (Member 4)")
    print("=" * 84)
    print(f"\nBaseline:    {comparison.baseline.scenario_name}")
    print(f"Alternative: {comparison.alternative.scenario_name}")
    print("\n" + "-" * 84)
    print(f"  {'Metric':<34}{'Baseline':>14}{'Alternative':>14}{'Difference':>14}")
    print("-" * 84)
    print(
        row(
            "Material emissions (t CO2e)",
            comparison.baseline.total_emissions_tonnes_co2e,
            comparison.alternative.total_emissions_tonnes_co2e,
            "",
        )
    )
    print(
        row(
            f"Cost ({comparison.currency})",
            comparison.cost_baseline,
            comparison.cost_alternative,
            "",
        )
    )
    print("-" * 84)
    print(
        f"  Emission reduction: {comparison.emissions_reduction_percent:.1f}% "
        f"({comparison.emissions_reduction_tonnes_co2e:,.1f} t CO2e)"
    )
    print(
        f"  Cost saving: {comparison.cost_saving:+,.0f} "
        f"{comparison.currency} "
        f"({comparison.cost_saving_percent:+.1f}%)"
        + (
            f" - {comparison.cost_per_tonne_avoided:+,.0f} "
            f"{comparison.currency} per tonne CO2e avoided"
            if comparison.cost_per_tonne_avoided is not None
            else ""
        )
    )
    print("\n  Material changes:")
    for delta in comparison.material_deltas:
        print(
            f"    - {delta.material_name} ({delta.change_type}): "
            f"{delta.emissions_delta_kg_co2e:+,.0f} kg CO2e"
        )
    print("\n  Warnings:")
    for warning in dict.fromkeys(comparison.warnings):
        print(f"    ! {warning}")
    print()


if __name__ == "__main__":
    _demo()
