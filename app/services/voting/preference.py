def build_ballots_for_motion(motion):
    votes_by_voter = {}
    for vote in motion.preference_votes:
        votes_by_voter.setdefault(vote.voter_id, []).append(vote)

    ballots = []
    for votes in votes_by_voter.values():
        sorted_votes = sorted(votes, key=lambda v: v.preference_rank)
        ballot = [v.option_id for v in sorted_votes]
        if ballot:
            ballots.append(ballot)

    return ballots


def irv_tie_break_loser(ballots, tied_candidates, options_by_id):
    log = []
    if not ballots:
        return None, log

    tied = set(tied_candidates)
    if len(tied) <= 1:
        return (next(iter(tied)) if tied else None), log

    def names(cids):
        return ", ".join(options_by_id[cid].text for cid in sorted(cids))

    log.append(f"Tie-break among {names(tied)} using rankings restricted to tied candidates.")

    while len(tied) > 1:
        filtered_ballots = []
        max_depth = 0
        for ballot in ballots:
            filtered = [cid for cid in ballot if cid in tied]
            if filtered:
                filtered_ballots.append(filtered)
                if len(filtered) > max_depth:
                    max_depth = len(filtered)

        if not filtered_ballots or max_depth == 0:
            log.append("No more useful preference information in restricted rankings.")
            break

        reduced = False
        for level in range(1, max_depth + 1):
            counts = {cid: 0 for cid in tied}
            for filtered in filtered_ballots:
                if len(filtered) >= level:
                    counts[filtered[level - 1]] += 1

            min_count = min(counts.values())
            lowest = [cid for cid, value in counts.items() if value == min_count]

            pretty_counts = ", ".join(
                f"{options_by_id[cid].text}: {counts[cid]}" for cid in sorted(tied)
            )
            log.append(f"  At preference position {level} (restricted), counts: {pretty_counts}.")

            if len(lowest) < len(tied):
                if len(lowest) == 1:
                    loser = lowest[0]
                    log.append(
                        f"  {options_by_id[loser].text} has the fewest appearances at this level "
                        "and is eliminated by tie-break (restricted rankings)."
                    )
                    return loser, log

                log.append(
                    f"  Lowest group at this level is {{ {names(lowest)} }}, "
                    "narrowing tie to this subset and restarting from top."
                )
                tied = set(lowest)
                reduced = True
                break

        if not reduced:
            log.append("Restricted rankings cannot narrow the tie further.")
            break

    if len(tied) == 1:
        loser = next(iter(tied))
        log.append(
            f"Restricted rankings eventually identify {options_by_id[loser].text} "
            "as the unique weakest candidate."
        )
        return loser, log

    log.append(
        "Falling back to original full rankings to break remaining tie among "
        f"{names(tied)}."
    )

    all_max_depth = max((len(ballot) for ballot in ballots), default=0)

    while len(tied) > 1 and all_max_depth > 0:
        reduced = False

        for level in range(1, all_max_depth + 1):
            counts = {cid: 0 for cid in tied}
            for ballot in ballots:
                if len(ballot) >= level:
                    candidate = ballot[level - 1]
                    if candidate in tied:
                        counts[candidate] += 1

            if all(value == 0 for value in counts.values()):
                continue

            min_count = min(counts.values())
            lowest = [cid for cid, value in counts.items() if value == min_count]
            pretty_counts = ", ".join(
                f"{options_by_id[cid].text}: {counts[cid]}" for cid in sorted(tied)
            )
            log.append(f"  At absolute ballot position {level}, counts: {pretty_counts}.")

            if len(lowest) < len(tied):
                if len(lowest) == 1:
                    loser = lowest[0]
                    log.append(
                        f"  {options_by_id[loser].text} is uniquely weakest at this position "
                        "and is eliminated by fallback tie-break."
                    )
                    return loser, log

                log.append(
                    f"  Lowest group is {{ {names(lowest)} }}, "
                    "narrowing tie to this subset and restarting from top."
                )
                tied = set(lowest)
                reduced = True
                break

        if not reduced:
            log.append("Original rankings also cannot narrow the tie further.")
            break

    if len(tied) == 1:
        loser = next(iter(tied))
        log.append(
            f"After considering original rankings, {options_by_id[loser].text} "
            "is the unique weakest candidate."
        )
        return loser, log

    log.append(
        "All deeper preference methods failed to break the tie; leaving final decision "
        "to deterministic fallback in caller."
    )
    return None, log


def irv_single_winner(ballots, active_candidates, options_by_id):
    active = set(active_candidates)
    rounds = []
    round_logs = []

    def name(cid):
        return options_by_id[cid].text

    while active:
        if len(active) == 1:
            (only,) = active
            round_logs.append([f"{name(only)} is the only remaining candidate and is elected."])
            return only, rounds, round_logs

        counts = {cid: 0 for cid in active}
        for ballot in ballots:
            for option_id in ballot:
                if option_id in active:
                    counts[option_id] += 1
                    break

        rounds.append(counts.copy())
        round_number = len(rounds)
        total_valid = sum(counts.values())

        base_log = [
            "Round {}: first-preference counts {}".format(
                round_number,
                ", ".join(f"{name(cid)} = {counts[cid]}" for cid in sorted(active)),
            ),
            f"Total valid ballots counted this round: {total_valid}.",
        ]

        if total_valid == 0:
            base_log.append("No more usable ballots; no winner can be determined.")
            round_logs.append(base_log)
            return None, rounds, round_logs

        winner_id = max(counts, key=counts.get)
        if counts[winner_id] > total_valid / 2:
            base_log.append(f"{name(winner_id)} has a majority (>50%) and is elected as winner.")
            round_logs.append(base_log)
            return winner_id, rounds, round_logs

        zero_candidates = [cid for cid, value in counts.items() if value == 0]
        non_zero_candidates = [cid for cid, value in counts.items() if value > 0]

        if zero_candidates and non_zero_candidates:
            if len(zero_candidates) == 1:
                zero_name = name(zero_candidates[0])
                base_log.append(
                    f"{zero_name} has 0 first-preference votes and is eliminated automatically."
                )
            else:
                zero_names = ", ".join(name(cid) for cid in sorted(zero_candidates))
                base_log.append(
                    "The following candidates have 0 first-preference votes and are "
                    f"all eliminated automatically: {zero_names}."
                )

            for candidate in zero_candidates:
                active.remove(candidate)

            round_logs.append(base_log)
            continue

        min_votes = min(counts.values())
        lowest = [cid for cid, value in counts.items() if value == min_votes]

        if len(lowest) == 1:
            loser = lowest[0]
            base_log.append(
                f"No majority. {name(loser)} has the fewest first-preference votes "
                f"({min_votes}) and is eliminated."
            )
        else:
            tied_names = ", ".join(name(cid) for cid in sorted(lowest))
            base_log.append(
                f"No majority. Tie for lowest between: {tied_names}. "
                "Applying deeper preference tie-break."
            )
            tie_loser, tie_log = irv_tie_break_loser(ballots, lowest, options_by_id)
            base_log.extend(tie_log)
            if tie_loser is None:
                tie_loser = min(lowest)
                base_log.append(
                    "Deep preference tie-break cannot distinguish; "
                    f"falling back to deterministic rule and eliminating {name(tie_loser)}."
                )
            else:
                base_log.append(f"Result of tie-break: {name(tie_loser)} is eliminated.")
            loser = tie_loser

        active.remove(loser)
        round_logs.append(base_log)

    round_logs.append(["All candidates eliminated; no winner determined."])
    return None, rounds, round_logs


def tally_preference_sequential_irv(motion):
    ballots = build_ballots_for_motion(motion)
    options_by_id = {option.id: option for option in motion.options}
    all_candidate_ids = set(options_by_id.keys())

    num_seats = motion.num_winners or 1
    winner_ids = []
    seats_info = []

    for seat_index in range(num_seats):
        active_candidates = all_candidate_ids - set(winner_ids)
        if not active_candidates:
            break

        winner_id, rounds_raw, round_logs = irv_single_winner(
            ballots, active_candidates, options_by_id
        )
        if winner_id is None:
            break

        winner_ids.append(winner_id)
        rounds_info = []
        for index, counts in enumerate(rounds_raw):
            counts_list = []
            for candidate_id, count in sorted(counts.items()):
                counts_list.append(
                    {"option": options_by_id[candidate_id], "count": count}
                )
            rounds_info.append(
                {
                    "round_number": index + 1,
                    "counts": counts_list,
                    "total": sum(counts.values()),
                }
            )

        seats_info.append(
            {
                "seat_number": seat_index + 1,
                "winner": options_by_id[winner_id],
                "rounds": rounds_info,
                "round_logs": round_logs,
            }
        )

    winners = [options_by_id[candidate_id] for candidate_id in winner_ids]

    return {
        "winners": winners,
        "seats": seats_info,
        "num_winners": num_seats,
        "total_ballots": len(ballots),
    }
