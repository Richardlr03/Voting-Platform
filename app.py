from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
import uuid
import os

app = Flask(__name__)

# --- Config ---
# SQLite DB file in the project folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key-change-later"  # needed later for sessions

db = SQLAlchemy(app)

# --- Models (simple for now) ---

class Meeting(db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # relationships
    motions = db.relationship("Motion", backref="meeting", lazy=True)
    voters = db.relationship("Voter", backref="meeting", lazy=True)


class Motion(db.Model):
    __tablename__ = "motions"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)

    # "YES_NO", "CANDIDATE", "PREFERENCE", etc.
    type = db.Column(db.String(50), nullable=False, default="YES_NO")

    # For systems with multiple winners (e.g. preference voting / STV)
    num_winners = db.Column(db.Integer, nullable=True)  # e.g. 1, 2, 3

    # "DRAFT", "OPEN", "CLOSED"
    status = db.Column(db.String(20), nullable=False, default="DRAFT")

    options = db.relationship("Option", backref="motion", lazy=True)
    votes = db.relationship("Vote", backref="motion", lazy=True)


class Option(db.Model):
    __tablename__ = "options"

    id = db.Column(db.Integer, primary_key=True)
    motion_id = db.Column(db.Integer, db.ForeignKey("motions.id"), nullable=False)
    text = db.Column(db.String(200), nullable=False)

    votes = db.relationship("Vote", backref="option", lazy=True)


class Voter(db.Model):
    __tablename__ = "voters"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)

    # unique code for this voter to access the voting page
    code = db.Column(db.String(50), unique=True, nullable=False)

    votes = db.relationship("Vote", backref="voter", lazy=True)


class Vote(db.Model):
    __tablename__ = "votes"

    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    motion_id = db.Column(db.Integer, db.ForeignKey("motions.id"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("options.id"), nullable=False)

    # For preference voting: 1 = first preference, 2 = second, etc.
    # For normal motions, this stays NULL.
    preference_rank = db.Column(db.Integer, nullable=True)

# --- Helper Functions ---

def generate_voter_code():
    # 8-character uppercase code, e.g. 'A1B2C3D4'
    return uuid.uuid4().hex[:8].upper()

def build_ballots_for_motion(motion):
    """
    Turn motion.votes into a list of ballots.
    Each ballot is a list of option_ids in rank order: [first, second, third, ...]
    Only uses votes with preference_rank not NULL.
    """
    # Group preference votes by voter
    votes_by_voter = {}
    for vote in motion.votes:
        if vote.preference_rank is not None:
            votes_by_voter.setdefault(vote.voter_id, []).append(vote)

    ballots = []
    for voter_id, votes in votes_by_voter.items():
        # sort by rank: 1,2,3,...
        sorted_votes = sorted(votes, key=lambda v: v.preference_rank)
        ballot = [v.option_id for v in sorted_votes]
        if ballot:
            ballots.append(ballot)

    return ballots

def irv_single_winner(ballots, active_candidates):
    active = set(active_candidates)
    rounds = []

    while active:
        if len(active) == 1:
            (only,) = active
            return only, rounds

        counts = {cid: 0 for cid in active}
        for ballot in ballots:
            for opt_id in ballot:
                if opt_id in active:
                    counts[opt_id] += 1
                    break

        rounds.append(counts.copy())

        total_valid = sum(counts.values())
        if total_valid == 0:
            return None, rounds

        winner_id = max(counts, key=counts.get)
        if counts[winner_id] > total_valid / 2:
            return winner_id, rounds

        min_votes = min(counts.values())
        lowest = [cid for cid, v in counts.items() if v == min_votes]

        if len(lowest) == 1:
            loser = lowest[0]
        else:
            tie_loser = irv_tie_break_loser(ballots, lowest)
            if tie_loser is None:
                tie_loser = min(lowest)  # final emergency fallback
            loser = tie_loser

        active.remove(loser)

    return None, rounds

def irv_tie_break_loser(ballots, tied_candidates):
    """
    Break a tie between candidates in tied_candidates using deeper preferences.

    Stage 1: relative to the tied set only
      - Filter each ballot to only tied candidates.
      - For rank level 1..max_depth in that filtered ranking:
          * Count how often each tied candidate appears at that level.
          * Find the candidates with the FEWEST appearances (weakest).
          * If that subset is:
              - size 1  -> eliminate that candidate
              - size >1 -> restrict tie to this subset and restart from level 1

    Stage 2 (fallback): use original full rankings
      - Do a similar process, but now counting appearances at absolute positions
        in the original ballots (no filtering), still only for tied candidates.

    If still tied after both stages, return None so caller can fall back
    to a final deterministic rule (e.g. lowest ID).
    """
    if not ballots:
        return None

    tied = set(tied_candidates)
    if len(tied) <= 1:
        return next(iter(tied)) if tied else None

    # -------- Stage 1: relative to tied set only --------
    while len(tied) > 1:
        filtered_ballots = []
        max_depth = 0
        for ballot in ballots:
            fb = [cid for cid in ballot if cid in tied]
            if fb:
                filtered_ballots.append(fb)
                if len(fb) > max_depth:
                    max_depth = len(fb)

        if not filtered_ballots or max_depth == 0:
            break

        reduced = False

        for level in range(1, max_depth + 1):
            counts = {cid: 0 for cid in tied}
            for fb in filtered_ballots:
                if len(fb) >= level:
                    cand_at_level = fb[level - 1]
                    counts[cand_at_level] += 1

            min_count = min(counts.values())
            lowest = [cid for cid, v in counts.items() if v == min_count]

            if len(lowest) < len(tied):
                if len(lowest) == 1:
                    return lowest[0]  # unique loser
                else:
                    tied = set(lowest)  # narrower tied set, restart from level 1
                    reduced = True
                    break

        if not reduced:
            break  # cannot narrow further in stage 1

    if len(tied) == 1:
        return next(iter(tied))

    # -------- Stage 2: fallback using original rankings --------
    # Now use absolute positions in original ballots, only counting tied candidates.
    all_max_depth = max((len(b) for b in ballots), default=0)

    while len(tied) > 1 and all_max_depth > 0:
        reduced = False

        for level in range(1, all_max_depth + 1):
            counts = {cid: 0 for cid in tied}
            for ballot in ballots:
                if len(ballot) >= level:
                    cand_at_level = ballot[level - 1]
                    if cand_at_level in tied:
                        counts[cand_at_level] += 1

            # If everyone has 0 at this level, nothing to learn; go to next level
            if all(v == 0 for v in counts.values()):
                continue

            min_count = min(counts.values())
            lowest = [cid for cid, v in counts.items() if v == min_count]

            if len(lowest) < len(tied):
                if len(lowest) == 1:
                    return lowest[0]  # unique loser in fallback stage
                else:
                    tied = set(lowest)
                    reduced = True
                    break  # restart from level 1 with smaller tied set

        if not reduced:
            break

    if len(tied) == 1:
        return next(iter(tied))

    # Still completely tied after both stages
    return None

def tally_preference_sequential_irv(motion):
    """
    Multi-winner sequential IRV for a PREFERENCE motion.

    - For seat 1: run IRV among all candidates.
    - For seat 2: run IRV again with the same ballots, but excluding already-elected winners.
    - Repeat until motion.num_winners winners are chosen or no more candidates.

    Returns a dict with:
      - winners: list of Option objects in election order
      - seats: list of per-seat info:
          {
            "seat_number": 1-based,
            "winner": Option,
            "rounds": [
              {
                "round_number": int,
                "counts": [ {"option": Option, "count": int}, ... ],
                "total": int,
              },
              ...
            ],
          }
      - num_winners: requested number of winners
      - total_ballots: number of preference ballots used
    """
    ballots = build_ballots_for_motion(motion)
    options_by_id = {opt.id: opt for opt in motion.options}
    all_candidate_ids = set(options_by_id.keys())

    num_seats = motion.num_winners or 1
    winners_ids = []
    seats_info = []

    for seat_index in range(num_seats):
        active_candidates = all_candidate_ids - set(winners_ids)
        if not active_candidates:
            break

        winner_id, rounds_raw = irv_single_winner(ballots, active_candidates)
        if winner_id is None:
            break

        winners_ids.append(winner_id)

        # Convert rounds into nicer structure for templates
        rounds_info = []
        for i, counts in enumerate(rounds_raw):
            total = sum(counts.values())
            counts_list = []
            for cid, cnt in sorted(counts.items()):
                counts_list.append({
                    "option": options_by_id[cid],
                    "count": cnt,
                })
            rounds_info.append({
                "round_number": i + 1,
                "counts": counts_list,
                "total": total,
            })

        seats_info.append({
            "seat_number": seat_index + 1,
            "winner": options_by_id[winner_id],
            "rounds": rounds_info,
        })

    winners = [options_by_id[cid] for cid in winners_ids]

    return {
        "winners": winners,
        "seats": seats_info,
        "num_winners": num_seats,
        "total_ballots": len(ballots),
    }

# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin/meetings")
def admin_meetings():
    # For now, just list all meetings in plain form
    meetings = Meeting.query.all()
    return render_template("admin/meetings.html", meetings=meetings)

@app.route("/admin/meetings/new", methods=["GET", "POST"])
def create_meeting():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")

        # Create and save meeting
        new_meeting = Meeting(title=title, description=description)
        db.session.add(new_meeting)
        db.session.commit()

        return redirect(url_for('admin_meetings'))

    # GET request → show form
    return render_template("admin/create_meeting.html")

@app.route("/admin/meetings/<int:meeting_id>")
def meeting_detail(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    return render_template("admin/meeting_detail.html", meeting=meeting)

@app.route("/admin/meetings/<int:meeting_id>/motions/new", methods=["GET", "POST"])
def create_motion(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == "POST":
        title = request.form.get("title")
        motion_type = request.form.get("type")
        candidate_text = request.form.get("candidates")
        num_winners_raw = request.form.get("num_winners")

        num_winners = None
        if motion_type == "PREFERENCE":
            try:
                nw = int(num_winners_raw) if num_winners_raw else 1
                if nw < 1:
                    nw = 1
                num_winners = nw
            except ValueError:
                num_winners = 1  # sensible default

        motion = Motion(
            meeting_id=meeting.id,
            title=title,
            type=motion_type,
            status="DRAFT",
            num_winners=num_winners,
        )
        db.session.add(motion)
        db.session.flush()  # get motion.id

        # Create options
        if motion_type == "YES_NO":
            default_options = ["Yes", "No", "Abstain"]
            for opt_text in default_options:
                db.session.add(Option(motion_id=motion.id, text=opt_text))

        elif motion_type in ("CANDIDATE", "PREFERENCE"):
            if candidate_text:
                lines = [line.strip() for line in candidate_text.splitlines() if line.strip()]
                for name in lines:
                    db.session.add(Option(motion_id=motion.id, text=name))

        db.session.commit()
        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    # GET
    return render_template("admin/create_motion.html", meeting=meeting)

@app.route("/admin/meetings/<int:meeting_id>/voters/new", methods=["GET", "POST"])
def create_voter(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == "POST":
        name = request.form.get("name")

        # Generate a unique code. In a real app you'd loop until unique;
        # for now we assume low collision chance.
        code = generate_voter_code()

        voter = Voter(
            meeting_id=meeting.id,
            name=name,
            code=code,
        )
        db.session.add(voter)
        db.session.commit()

        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    # GET -> show form
    return render_template("admin/create_voter.html", meeting=meeting)

@app.route("/admin/meetings/<int:meeting_id>/results")
def meeting_results(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    results = []

    for motion in meeting.motions:
        if motion.type == "PREFERENCE":
            pref_result = tally_preference_sequential_irv(motion)
            results.append({
                "motion": motion,
                "is_preference": True,
                "pref": pref_result,
            })
        else:
            # existing simple tally for YES_NO / CANDIDATE etc.
            option_counts = {opt.id: 0 for opt in motion.options}
            for vote in motion.votes:
                if vote.preference_rank is None:
                    if vote.option_id in option_counts:
                        option_counts[vote.option_id] += 1

            total_votes = sum(option_counts.values())

            option_results = []
            for opt in motion.options:
                count = option_counts.get(opt.id, 0)
                percent = (count / total_votes * 100) if total_votes > 0 else 0
                option_results.append({
                    "option": opt,
                    "count": count,
                    "percent": percent,
                })

            results.append({
                "motion": motion,
                "is_preference": False,
                "simple": {
                    "total_votes": total_votes,
                    "option_results": option_results,
                }
            })

    return render_template(
        "admin/meeting_results.html",
        meeting=meeting,
        results=results,
    )

@app.route("/admin/meetings/<int:meeting_id>/votes")
def meeting_votes(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    motions_detail = []

    for motion in meeting.motions:
        # Group votes by voter for this motion
        voter_map = {}  # voter_id -> {"voter": Voter, "votes": [Vote]}

        for vote in motion.votes:
            if vote.voter_id not in voter_map:
                voter_map[vote.voter_id] = {"voter": vote.voter, "votes": []}
            voter_map[vote.voter_id]["votes"].append(vote)

        rows = []

        for voter_id, data in voter_map.items():
            voter = data["voter"]
            vote_list = data["votes"]

            if motion.type == "PREFERENCE":
                # Sort by preference rank (1, 2, 3, ...). Unranked last just in case.
                sorted_votes = sorted(
                    vote_list,
                    key=lambda v: v.preference_rank if v.preference_rank is not None else 9999
                )

                parts = []
                for v in sorted_votes:
                    if v.preference_rank is not None:
                        parts.append(f"{v.preference_rank}: {v.option.text}")
                    else:
                        parts.append(v.option.text)
                choice_display = ", ".join(parts)
            else:
                # Simple motions: YES_NO, CANDIDATE, etc.
                choices = [v.option.text for v in vote_list]
                choice_display = ", ".join(choices)

            rows.append({
                "voter": voter,
                "choice_display": choice_display,
            })

        # Sort rows alphabetically by voter name
        rows.sort(key=lambda r: r["voter"].name.lower())

        motions_detail.append({
            "motion": motion,
            "rows": rows,
            "num_voters_voted": len(voter_map),
            "num_possible_voters": len(meeting.voters),
        })

    return render_template(
        "admin/meeting_votes.html",
        meeting=meeting,
        motions_detail=motions_detail,
    )


@app.route("/vote/<code>")
def voter_dashboard(code):
    voter = Voter.query.filter_by(code=code).first()

    if not voter:
        return render_template(
            "voter/motion_list.html",
            invalid=True,
            voter=None,
            meeting=None,
            motions=None,
            voted_motion_ids=set(),
        )

    meeting = voter.meeting
    motions = meeting.motions

    # Figure out which motions this voter has already cast any vote for
    voted_motion_ids = set()
    for vote in voter.votes:
        voted_motion_ids.add(vote.motion_id)

    return render_template(
        "voter/motion_list.html",
        invalid=False,
        voter=voter,
        meeting=meeting,
        motions=motions,
        voted_motion_ids=voted_motion_ids,
    )

@app.route("/vote/<code>/motion/<int:motion_id>", methods=["GET", "POST"])
def vote_motion(code, motion_id):
    voter = Voter.query.filter_by(code=code).first()

    if not voter:
        # Reuse the same template with invalid flag
        return render_template(
            "voter/vote_motion.html",
            invalid=True,
            voter=None,
            meeting=None,
            motion=None,
            simple_vote=None,
            preference_ranks=None,
        )

    meeting = voter.meeting

    # Make sure the motion belongs to this meeting
    motion = Motion.query.filter_by(id=motion_id, meeting_id=meeting.id).first_or_404()

    # Load existing votes for this motion & voter
    simple_vote = None
    preference_ranks = {}

    votes_for_motion = [v for v in voter.votes if v.motion_id == motion.id]

    for v in votes_for_motion:
        if v.preference_rank is None:
            simple_vote = v
        else:
            preference_ranks[v.option_id] = v.preference_rank

    if request.method == "POST":
        if motion.type == "PREFERENCE":
            # Delete old preference votes for this motion & voter
            existing_pref_votes = Vote.query.filter(
                and_(
                    Vote.voter_id == voter.id,
                    Vote.motion_id == motion.id,
                    Vote.preference_rank.isnot(None),
                )
            ).all()
            for ev in existing_pref_votes:
                db.session.delete(ev)

            # Collect new ranks
            ranks = []
            for opt in motion.options:
                field_name = f"opt_{opt.id}_rank"
                value = request.form.get(field_name)
                if not value:
                    continue
                try:
                    rank = int(value)
                except ValueError:
                    continue
                if rank <= 0:
                    continue
                ranks.append((rank, opt.id))

            # Save new preference votes
            for rank, opt_id in ranks:
                db.session.add(Vote(
                    voter_id=voter.id,
                    motion_id=motion.id,
                    option_id=opt_id,
                    preference_rank=rank,
                ))

        else:
            # YES_NO / CANDIDATE: single choice
            selected_option_id = request.form.get("option")
            if selected_option_id:
                try:
                    option_id_int = int(selected_option_id)
                except ValueError:
                    option_id_int = None

                if option_id_int is not None:
                    if simple_vote:
                        simple_vote.option_id = option_id_int
                        simple_vote.preference_rank = None
                    else:
                        db.session.add(Vote(
                            voter_id=voter.id,
                            motion_id=motion.id,
                            option_id=option_id_int,
                            preference_rank=None,
                        ))

        db.session.commit()
        flash("Your vote for this motion has been recorded.", "success")
        # After voting, send them back to the motion list
        return redirect(url_for("voter_dashboard", code=voter.code))

    # GET: show form with any existing choices prefilled
    return render_template(
        "voter/vote_motion.html",
        invalid=False,
        voter=voter,
        meeting=meeting,
        motion=motion,
        simple_vote=simple_vote,
        preference_ranks=preference_ranks,
    )

if __name__ == "__main__":
    app.run(debug=True)