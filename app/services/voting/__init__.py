from app.services.voting.candidate import tally_candidate_election
from app.services.voting.preference import tally_preference_sequential_irv

__all__ = ["tally_candidate_election", "tally_preference_sequential_irv"]
