def tally_yes_no_abstain(motion):
    options_by_id = {option.id: option for option in motion.options}
    option_counts = {option_id: 0 for option_id in options_by_id}

    for vote in motion.yes_no_votes:
        if vote.option_id in option_counts:
            option_counts[vote.option_id] += 1

    def is_label(option, label):
        return (option.text or "").strip().lower() == label

    yes_ids = [option.id for option in motion.options if is_label(option, "yes")]
    no_ids = [option.id for option in motion.options if is_label(option, "no")]
    abstain_ids = [option.id for option in motion.options if is_label(option, "abstain")]

    yes_votes = sum(option_counts.get(option_id, 0) for option_id in yes_ids)
    no_votes = sum(option_counts.get(option_id, 0) for option_id in no_ids)
    abstain_votes = sum(option_counts.get(option_id, 0) for option_id in abstain_ids)

    total_votes = sum(option_counts.values())
    decisive_votes = yes_votes + no_votes

    if decisive_votes == 0:
        decision = "NO_DECISION"
    elif yes_votes > no_votes:
        decision = "PASSED"
    elif no_votes > yes_votes:
        decision = "FAILED"
    else:
        decision = "TIED"

    order = {"yes": 0, "no": 1, "abstain": 2}
    option_results = []
    for option in motion.options:
        count = option_counts.get(option.id, 0)
        percent = (count / total_votes * 100) if total_votes > 0 else 0
        option_results.append({"option": option, "count": count, "percent": percent})

    option_results.sort(
        key=lambda row: (
            order.get((row["option"].text or "").strip().lower(), 99),
            row["option"].text.lower(),
            row["option"].id,
        )
    )

    return {
        "total_votes": total_votes,
        "decisive_votes": decisive_votes,
        "yes_votes": yes_votes,
        "no_votes": no_votes,
        "abstain_votes": abstain_votes,
        "decision": decision,
        "option_results": option_results,
    }
