"""Resource harvesting system.

Manages the loop of attacking harvestable props, decrementing their hit
counters, rolling deterministic drops from a drop table, and adding the
resulting items to the player's inventory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from procengine.game.game_api import GameWorld, Player, Prop


@dataclass
class HarvestResult:
    """Outcome of a single harvest attempt."""

    hit: bool = False
    target_name: str = ""
    hits_remaining: int = 0
    destroyed: bool = False
    drops: List[Dict[str, Any]] = field(default_factory=list)
    on_cooldown: bool = False


class HarvestingSystem:
    """Manages resource harvesting from props via the attack input.

    Parameters
    ----------
    drop_tables:
        Mapping of ``prop_type`` to drop-table entries loaded from
        ``data/items/resource_drops.json``.
    seed:
        Root seed used for deterministic drop quantity rolls.
    attack_interval:
        Minimum seconds between swings.
    attack_range:
        Maximum distance (metres) at which a prop can be hit.
    """

    def __init__(
        self,
        drop_tables: Dict[str, Any],
        seed: int = 0,
        *,
        attack_interval: float = 0.4,
        attack_range: float = 3.0,
    ) -> None:
        self._drop_tables = drop_tables
        self._rng = np.random.Generator(np.random.PCG64(seed))
        self._attack_cooldown: float = 0.0
        self._attack_interval = attack_interval
        self._attack_range = attack_range

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def try_harvest(
        self,
        player: "Player",
        world: "GameWorld",
    ) -> HarvestResult:
        """Attempt to harvest the nearest harvestable prop in range.

        Called when the player presses the attack button.  Finds the
        closest ``Prop`` with ``interaction_action == "harvest"`` within
        ``attack_range``, decrements its hit counter, and—when the
        counter reaches zero—rolls drops and destroys the prop.

        Returns
        -------
        HarvestResult
            Describes whether anything was hit, what was destroyed, and
            what items were gained.
        """
        if self._attack_cooldown > 0:
            return HarvestResult(on_cooldown=True)

        # Start cooldown immediately
        self._attack_cooldown = self._attack_interval

        from procengine.game.game_api import Prop

        nearby = world.get_entities_in_range(player.position, self._attack_range)

        best_prop: Optional[Prop] = None
        best_dist = float("inf")

        for entity in nearby:
            if entity.entity_id == player.entity_id:
                continue
            if not isinstance(entity, Prop):
                continue
            if not entity.is_harvestable:
                continue

            dist = (entity.position - player.position).length()
            if dist < best_dist:
                best_prop = entity
                best_dist = dist

        if best_prop is None:
            return HarvestResult()

        # Apply hit
        remaining = best_prop.state.get("hits_remaining", 1) - 1
        best_prop.state["hits_remaining"] = max(remaining, 0)

        display_name = best_prop.prop_type.replace("_", " ").title()

        if remaining > 0:
            return HarvestResult(
                hit=True,
                target_name=display_name,
                hits_remaining=remaining,
            )

        # Prop destroyed — roll drops
        drops = self._roll_drops(best_prop.prop_type)

        for drop in drops:
            player.inventory.add_item(drop["item_id"], drop["count"])

        world.destroy_entity(best_prop.entity_id)

        return HarvestResult(
            hit=True,
            target_name=display_name,
            hits_remaining=0,
            destroyed=True,
            drops=drops,
        )

    def update(self, dt: float) -> None:
        """Tick the attack cooldown timer."""
        if self._attack_cooldown > 0:
            self._attack_cooldown = max(0.0, self._attack_cooldown - dt)

    def get_drop_table(self, prop_type: str) -> Optional[Dict[str, Any]]:
        """Return the drop table entry for *prop_type*, or ``None``."""
        return self._drop_tables.get(prop_type)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _roll_drops(self, prop_type: str) -> List[Dict[str, Any]]:
        """Roll drop quantities for *prop_type* using the deterministic RNG."""
        table = self._drop_tables.get(prop_type)
        if not table:
            return []

        result: List[Dict[str, Any]] = []
        for entry in table.get("drops", []):
            lo = entry.get("min", 0)
            hi = entry.get("max", 1)
            count = int(self._rng.integers(lo, hi + 1))  # inclusive upper bound
            if count > 0:
                result.append({"item_id": entry["item_id"], "count": count})

        return result
