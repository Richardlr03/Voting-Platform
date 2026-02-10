from app.services.voting.candidate import tally_candidate_election
from app.services.voting.cumulative import tally_cumulative_votes
from app.services.voting.preference import tally_preference_sequential_irv
from app.services.voting.score import tally_score_votes
from app.services.voting.yes_no import tally_yes_no_abstain

__all__ = [
    "tally_candidate_election",
    "tally_cumulative_votes",
    "tally_preference_sequential_irv",
    "tally_score_votes",
    "tally_yes_no_abstain",
]
