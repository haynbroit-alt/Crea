from datetime import datetime, timezone

from app.world.catalog import get_memory, next_dilemma
from app.world.state import get_world, save_world, _lock, _load, _save
from app.world.narrator import generate_script


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

        votes = world["vote_counts"]
        # Tiebreaker: A wins on tie (Council of Elders casts deciding vote)
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
            "vote_result": {"winner": winner, "votes": dict(votes)},
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
            # All memories exhausted
            world["current_dilemma"] = None
            world["voting_open"] = False

        _save(world)
        return episode
