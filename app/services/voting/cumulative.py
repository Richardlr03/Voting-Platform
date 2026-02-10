def tally_cumulative_votes(motion):
    options_by_id = {option.id: option for option in motion.options}
    totals = {option_id: 0.0 for option_id in options_by_id}
    counts = {option_id: 0 for option_id in options_by_id}
    level_counts = {option_id: {} for option_id in options_by_id}

    observed_points = set()
    voter_ids = set()

    for vote in motion.cumulative_votes:
        if vote.option_id in totals:
            points_value = float(vote.points)
            totals[vote.option_id] += points_value
            counts[vote.option_id] += 1
            level_counts[vote.option_id][points_value] = (
                level_counts[vote.option_id].get(points_value, 0) + 1
            )
            observed_points.add(points_value)
            voter_ids.add(vote.voter_id)

    results = []
    for option_id, option in options_by_id.items():
        total = totals[option_id]
        results.append({"option": option, "total": total})

    results.sort(
        key=lambda row: (
            -row["total"],
            row["option"].id,
        )
    )

    winner = None
    winners = []
    tie_break_level = None
    deadlock = False

    if results:
        max_total = results[0]["total"]
        tied = [row["option"].id for row in results if row["total"] == max_total]

        if len(tied) == 1:
            winner = options_by_id[tied[0]]
            winners = [winner]
        else:
            point_levels = sorted(observed_points, reverse=True)

            remaining = tied
            for level in point_levels:
                counts_at_level = {
                    option_id: level_counts[option_id].get(level, 0)
                    for option_id in remaining
                }
                max_count = max(counts_at_level.values(), default=0)
                top = [
                    option_id
                    for option_id, value in counts_at_level.items()
                    if value == max_count
                ]
                if len(top) == 1:
                    winner = options_by_id[top[0]]
                    winners = [winner]
                    tie_break_level = level
                    break
                remaining = top

            if winner is None:
                deadlock = True
                winners = [options_by_id[option_id] for option_id in remaining]

    return {
        "total_votes": sum(counts.values()),
        "ballot_count": len(voter_ids),
        "results": results,
        "winner": winner,
        "winners": winners,
        "is_tie": len(winners) > 1,
        "tie_break_level": tie_break_level,
        "deadlock": deadlock,
    }
