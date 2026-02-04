def tally_candidate_election(motion):
    options_by_id = {option.id: option for option in motion.options}
    option_counts = {option_id: 0 for option_id in options_by_id}

    for vote in motion.candidate_votes:
        if vote.option_id in option_counts:
            option_counts[vote.option_id] += 1

    total_votes = sum(option_counts.values())
    max_votes = max(option_counts.values(), default=0)

    winners = []
    if max_votes > 0:
        winners = [
            options_by_id[option_id]
            for option_id, count in option_counts.items()
            if count == max_votes
        ]

    option_results = []
    for option in motion.options:
        count = option_counts.get(option.id, 0)
        percent = (count / total_votes * 100) if total_votes > 0 else 0
        option_results.append({"option": option, "count": count, "percent": percent})

    option_results.sort(
        key=lambda row: (-row["count"], row["option"].text.lower(), row["option"].id)
    )

    return {
        "total_votes": total_votes,
        "option_results": option_results,
        "winner": winners[0] if len(winners) == 1 else None,
        "winners": winners,
        "is_tie": len(winners) > 1,
        "top_vote_count": max_votes,
    }
