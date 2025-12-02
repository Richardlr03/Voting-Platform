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

def generate_voter_code():
    # 8-character uppercase code, e.g. 'A1B2C3D4'
    return uuid.uuid4().hex[:8].upper()

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
        # Initialize counts per option
        option_counts = {opt.id: 0 for opt in motion.options}

        # Count votes
        for vote in motion.votes:
            if vote.option_id in option_counts:
                option_counts[vote.option_id] += 1

        total_votes = sum(option_counts.values())

        option_results = []
        for opt in motion.options:
            count = option_counts[opt.id]
            percent = (count / total_votes * 100) if total_votes > 0 else 0
            option_results.append({
                "option": opt,
                "count": count,
                "percent": percent,
            })

        results.append({
            "motion": motion,
            "total_votes": total_votes,
            "option_results": option_results,
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


@app.route("/vote/<code>", methods=["GET", "POST"])
def voter_page(code):
    voter = Voter.query.filter_by(code=code).first()

    if not voter:
        # Invalid code: show error
        return render_template(
            "voter/vote.html",
            invalid=True,
            voter=None,
            meeting=None,
            motions=None,
            votes_by_motion=None,
            preference_ranks_by_motion=None,
        )

    meeting = voter.meeting
    motions = meeting.motions

    # For non-preference motions, we still want a simple "one vote per motion" mapping
    simple_votes_by_motion = {
        vote.motion_id: vote
        for vote in voter.votes
        if vote.preference_rank is None
    }

    preference_ranks_by_motion = {}
    for vote in voter.votes:
        if vote.preference_rank is not None:
            motion_map = preference_ranks_by_motion.setdefault(vote.motion_id, {})
            motion_map[vote.option_id] = vote.preference_rank

    if request.method == "POST":
        for motion in motions:
            # Preference voting: ranked ballot
            if motion.type == "PREFERENCE":
                # Delete existing preference votes for this voter & motion
                existing_pref_votes = Vote.query.filter(
                    and_(
                        Vote.voter_id == voter.id,
                        Vote.motion_id == motion.id,
                        Vote.preference_rank.isnot(None),
                    )
                ).all()
                for ev in existing_pref_votes:
                    db.session.delete(ev)

                # Read all rank inputs for this motion
                ranks = []  # list of (rank, option_id)
                for opt in motion.options:
                    field_name = f"motion_{motion.id}_opt_{opt.id}_rank"
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

                # Save new preference votes (one row per ranked option)
                for rank, opt_id in ranks:
                    db.session.add(Vote(
                        voter_id=voter.id,
                        motion_id=motion.id,
                        option_id=opt_id,
                        preference_rank=rank,
                    ))

            else:
                # Existing behaviour: YES_NO or CANDIDATE (single choice)
                field_name = f"motion_{motion.id}"
                selected_option_id = request.form.get(field_name)

                if not selected_option_id:
                    continue

                try:
                    option_id_int = int(selected_option_id)
                except ValueError:
                    continue

                existing_vote = simple_votes_by_motion.get(motion.id)

                if existing_vote:
                    existing_vote.option_id = option_id_int
                else:
                    db.session.add(Vote(
                        voter_id=voter.id,
                        motion_id=motion.id,
                        option_id=option_id_int,
                        preference_rank=None,
                    ))

        db.session.commit()
        flash("Your votes have been recorded (including any preferences).", "success")
        return redirect(url_for("voter_page", code=voter.code))

    # GET – we only pre-fill non-preference votes for now
    return render_template(
        "voter/vote.html",
        invalid=False,
        voter=voter,
        meeting=meeting,
        motions=motions,
        votes_by_motion=simple_votes_by_motion,
        preference_ranks_by_motion=preference_ranks_by_motion,
    )

if __name__ == "__main__":
    app.run(debug=True)