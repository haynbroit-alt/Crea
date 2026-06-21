from datetime import datetime, timezone

from app.world.catalog import get_memory, next_dilemma
from app.world.state import get_world, save_world, _lock, _load, _save
from app.world.narrator import generate_script

_SHADOW_LOG_MAX = 10


def _corruption_level(sanity: int) -> float:
    """0.0 at sanity ≥ 50; rises linearly to 1.0 at sanity = 0."""
    return round(max(0.0, (50 - sanity) / 50), 3)


def _npc_preferred_option(world: dict) -> str:
    """
    Panicked NPCs sacrifice the most abstract memory to protect concrete ones.
    Higher tier = more abstract (tier 3 = existential, tier 1 = sensory).
    """
    dilemma = world.get("current_dilemma")
    if not dilemma:
        return "A"
    tier_a = get_memory(dilemma["option_A"]["sacrifice"]).get("tier", 1)
    tier_b = get_memory(dilemma["option_B"]["sacrifice"]).get("tier", 1)
    if tier_a > tier_b:
        return "A"
    if tier_b > tier_a:
        return "B"
    # Same tier: mirror real majority
    votes = world["vote_counts"]
    return "A" if votes.get("A", 0) >= votes.get("B", 0) else "B"


def _inject_ghost_votes(world: dict, corruption: float) -> int:
    """
    When corruption > 0.3, panicked NPCs inject phantom votes.
    Returns ghost vote count (0 if below threshold or no real votes).
    """
    if corruption <= 0.3:
        return 0
    total_real = sum(world["vote_counts"].values())
    if total_real == 0:
        return 0
    phantom_count = int(total_real * corruption * 0.5)
    world["vote_counts"][_npc_preferred_option(world)] += phantom_count
    return phantom_count


def _append_shadow_log(world: dict, day: int, phantom_count: int) -> None:
    log = world.setdefault("shadow_log", [])
    log.append(
        f"[SYS_ERR_D{day:03d}] {phantom_count} anomalie(s) dans le registre. "
        "Origine : non résolue. Intégrité des données : compromise."
    )
    world["shadow_log"] = log[-_SHADOW_LOG_MAX:]


def advance_day() -> dict:
    """
    Close today's vote, apply the result, generate today's episode,
    then set up the dilemma for tomorrow.
    Returns the completed episode.
    """
    with _lock:
        world = _load()
        if not world:
            raise RuntimeError("World not initialised")
        if not world.get("voting_open"):
            raise RuntimeError("Voting is already closed for today")

        # ── Corruption & ghost votes (before winner is decided) ───────────────
        corruption = _corruption_level(world["collective_sanity"])
        world["system_corruption_level"] = corruption
        phantom_count = _inject_ghost_votes(world, corruption)
        if phantom_count:
            _append_shadow_log(world, world["day"], phantom_count)

        # ── Winner determination ──────────────────────────────────────────────
        votes = world["vote_counts"]
        winner = "A" if votes.get("A", 0) >= votes.get("B", 0) else "B"
        losing_option = "B" if winner == "A" else "A"

        winning_dilemma = world["current_dilemma"][f"option_{winner}"]
        losing_dilemma = world["current_dilemma"][f"option_{losing_option}"]

        protected_id = winning_dilemma["protect"]
        lost_id = winning_dilemma["sacrifice"]

        # Apply memory loss
        if lost_id not in world["lost_memories"]:
            world["lost_memories"].append(lost_id)
        if lost_id in world["alive_memories"]:
            world["alive_memories"].remove(lost_id)

        # Apply protected memory
        if protected_id and protected_id not in world["protected_memories"]:
            world["protected_memories"].append(protected_id)

        # Apply world-stat impacts
        mem = get_memory(lost_id)
        impact = mem.get("loss_impact", {})
        for stat, delta in impact.items():
            world[stat] = max(0, min(100, world.get(stat, 100) + delta))

        # Generate episode script for this day
        world["voting_open"] = False
        episode = generate_script(world, lost_today_id=lost_id)
        episode.update({
            "vote_result": {
                "winner": winner,
                "votes": dict(votes),
                "phantom_votes": phantom_count or None,
            },
            "protected": protected_id,
            "lost": lost_id,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        world["episodes"].append(episode)

        # Advance to next day
        world["day"] += 1
        world["vote_counts"] = {"A": 0, "B": 0}
        world["voting_open"] = True

        # Build next dilemma
        pair = next_dilemma(world["day"], world["lost_memories"])
        if pair:
            mem_a, mem_b = pair
            world["current_dilemma"] = {
                "threat": (
                    "La Brume revient cette nuit. "
                    "Le Conseil peut en protéger un seul. "
                    "L'autre disparaîtra à l'aube."
                ),
                "option_A": {
                    "protect": mem_a,
                    "sacrifice": mem_b,
                    "label_protect": get_memory(mem_a)["name"],
                    "label_sacrifice": get_memory(mem_b)["name"],
                },
                "option_B": {
                    "protect": mem_b,
                    "sacrifice": mem_a,
                    "label_protect": get_memory(mem_b)["name"],
                    "label_sacrifice": get_memory(mem_a)["name"],
                },
            }
        else:
            world["current_dilemma"] = None
            world["voting_open"] = False

        _save(world)
        return episode
