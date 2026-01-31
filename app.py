from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
import uuid
import os
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import smtplib
from email.message import EmailMessage
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

# --- Config ---
# SQLite DB file in the project folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://TAMLZ03:20050329@localhost:3306/voting?charset=utf8mb4"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key-change-later"  # needed later for sessions
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect here if @login_required is triggered

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Models ---

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False) # Store email
    password_hash = db.Column(db.String(256), nullable=False) # Store hashed passwords

    meetings = db.relationship("Meeting", backref="admin", lazy=True)

class Meeting(db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

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

def _reset_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])

def generate_reset_token(email):
    return _reset_serializer().dumps(email, salt="password-reset")

def verify_reset_token(token, max_age=1800):
    try:
        return _reset_serializer().loads(token, salt="password-reset", max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def send_reset_email(to_email, reset_url):
    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        raise RuntimeError("Email credentials are not configured.")

    msg = EmailMessage()
    msg["Subject"] = "Reset your Voting Platform password"
    msg["From"] = app.config["MAIL_DEFAULT_SENDER"]
    msg["To"] = to_email
    msg.set_content(
        "You requested a password reset for Voting Platform.\n\n"
        f"Reset your password here: {reset_url}\n\n"
        "This link will expire in 30 minutes. If you did not request this, ignore this email."
    )

    with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as server:
        if app.config["MAIL_USE_TLS"]:
            server.starttls()
        server.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
        server.send_message(msg)
        app.logger.info("Password reset email sent to %s", to_email)

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

def irv_single_winner(ballots, active_candidates, options_by_id):
    """
    Run IRV for a single winner among active_candidates.

    Returns (winner_id, rounds, round_logs) where:
      - winner_id: option_id or None
      - rounds: list of {candidate_id: votes} dicts (one per round)
      - round_logs: list of list-of-strings; each element corresponds to a round
                    and contains human-readable explanation lines for that round.
    """
    active = set(active_candidates)
    rounds = []
    round_logs = []

    def name(cid):
        return options_by_id[cid].text

    while active:
        # If only one candidate left, they win automatically
        if len(active) == 1:
            (only,) = active
            round_logs.append([f"{name(only)} is the only remaining candidate and is elected."])
            return only, rounds, round_logs

        # Count first-choice votes among active candidates
        counts = {cid: 0 for cid in active}
        for ballot in ballots:
            for opt_id in ballot:
                if opt_id in active:
                    counts[opt_id] += 1
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

        # Check for majority (>50%)
        winner_id = max(counts, key=counts.get)
        if counts[winner_id] > total_valid / 2:
            base_log.append(
                f"{name(winner_id)} has a majority (>50%) and is elected as winner."
            )
            round_logs.append(base_log)
            return winner_id, rounds, round_logs

        # 🔹 NEW RULE: auto-eliminate any candidates with 0 first-preference votes
        zero_candidates = [cid for cid, v in counts.items() if v == 0]
        non_zero_candidates = [cid for cid, v in counts.items() if v > 0]

        # If some candidates have 0 and some have >0, eliminate all zero-vote candidates
        if zero_candidates and non_zero_candidates:
            if len(zero_candidates) == 1:
                z = zero_candidates[0]
                base_log.append(
                    f"{name(z)} has 0 first-preference votes and is eliminated automatically."
                )
            else:
                zero_names = ", ".join(name(cid) for cid in sorted(zero_candidates))
                base_log.append(
                    "The following candidates have 0 first-preference votes and are "
                    f"all eliminated automatically: {zero_names}."
                )

            # Remove all zero-vote candidates from active set
            for z in zero_candidates:
                active.remove(z)

            # Finish this round and continue with reduced active set
            round_logs.append(base_log)
            continue

        # No zero-vote candidates (or everyone is zero, which we already handled),
        # so we fall back to normal lowest-vote elimination + tie-break.
        min_votes = min(counts.values())
        lowest = [cid for cid, v in counts.items() if v == min_votes]

        if len(lowest) == 1:
            loser = lowest[0]
            base_log.append(
                f"No majority. {name(loser)} has the fewest first-preference votes "
                f"({min_votes}) and is eliminated."
            )
        else:
            # Tie at the bottom (partial or full) → use deeper-pref tiebreak
            tied_names = ", ".join(name(cid) for cid in sorted(lowest))
            base_log.append(
                f"No majority. Tie for lowest between: {tied_names}. "
                "Applying deeper preference tie-break."
            )
            tie_loser, tie_log = irv_tie_break_loser(ballots, lowest, options_by_id)
            base_log.extend(tie_log)
            if tie_loser is None:
                # Still tied even after deeper prefs → pick a stable fallback
                tie_loser = min(lowest)
                base_log.append(
                    f"Deep preference tie-break cannot distinguish; "
                    f"falling back to deterministic rule and eliminating {name(tie_loser)}."
                )
            else:
                base_log.append(f"Result of tie-break: {name(tie_loser)} is eliminated.")
            loser = tie_loser

        active.remove(loser)
        round_logs.append(base_log)
        # Continue loop with reduced active set

    # If we somehow exit loop with no active candidates
    round_logs.append(["All candidates eliminated; no winner determined."])
    return None, rounds, round_logs

def irv_tie_break_loser(ballots, tied_candidates, options_by_id):
    """
    Break a tie between candidates in tied_candidates using deeper preferences.

    Returns (loser_id, log_lines).

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
    """
    log = []
    if not ballots:
        return None, log

    tied = set(tied_candidates)
    if len(tied) <= 1:
        return (next(iter(tied)) if tied else None), log

    def names(cids):
        return ", ".join(options_by_id[cid].text for cid in sorted(cids))

    # -------- Stage 1: relative to tied set only --------
    log.append(f"Tie-break among {names(tied)} using rankings restricted to tied candidates.")

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
            log.append("No more useful preference information in restricted rankings.")
            break

        reduced = False

        for level in range(1, max_depth + 1):
            counts = {cid: 0 for cid in tied}
            for fb in filtered_ballots:
                if len(fb) >= level:
                    cand_at_level = fb[level - 1]
                    counts[cand_at_level] += 1

            # Everyone might be zero at this level; still handled by min()
            min_count = min(counts.values())
            lowest = [cid for cid, v in counts.items() if v == min_count]

            pretty_counts = ", ".join(
                f"{options_by_id[cid].text}: {counts[cid]}"
                for cid in sorted(tied)
            )
            log.append(f"  At preference position {level} (restricted), counts: {pretty_counts}.")

            if len(lowest) < len(tied):
                # We managed to narrow down to the "worst" subset
                if len(lowest) == 1:
                    loser = lowest[0]
                    log.append(
                        f"  {options_by_id[loser].text} has the fewest appearances at this level "
                        f"and is eliminated by tie-break (restricted rankings)."
                    )
                    return loser, log
                else:
                    log.append(
                        f"  Lowest group at this level is {{ {names(lowest)} }}, "
                        "narrowing tie to this subset and restarting from top."
                    )
                    tied = set(lowest)
                    reduced = True
                    break

        if not reduced:
            log.append("Restricted rankings cannot narrow the tie further.")
            break  # cannot narrow further in stage 1

    if len(tied) == 1:
        loser = next(iter(tied))
        log.append(
            f"Restricted rankings eventually identify {options_by_id[loser].text} "
            "as the unique weakest candidate."
        )
        return loser, log

    # -------- Stage 2: fallback using original rankings --------
    log.append(
        "Falling back to original full rankings to break remaining tie among "
        f"{names(tied)}."
    )

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

            if all(v == 0 for v in counts.values()):
                continue  # nothing to learn at this level

            min_count = min(counts.values())
            lowest = [cid for cid, v in counts.items() if v == min_count]

            pretty_counts = ", ".join(
                f"{options_by_id[cid].text}: {counts[cid]}"
                for cid in sorted(tied)
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
                else:
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

    # Still completely tied after both stages
    log.append(
        "All deeper preference methods failed to break the tie; leaving final decision "
        "to deterministic fallback in caller."
    )
    return None, log

def tally_preference_sequential_irv(motion):
    """
    Multi-winner sequential IRV for a PREFERENCE motion.

    Returns a dict with:
      - winners: list of Option objects in election order
      - seats: list of per-seat info:
          {
            "seat_number": int,
            "winner": Option,
            "rounds": [  # per-round counts for table display
              {
                "round_number": int,
                "counts": [ {"option": Option, "count": int}, ... ],
                "total": int,
              },
              ...
            ],
            "round_logs": [ [line1, line2, ...], ... ],  # narrative per round
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

        winner_id, rounds_raw, round_logs = irv_single_winner(
            ballots, active_candidates, options_by_id
        )
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
            "round_logs": round_logs,
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

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Create new user and hash the password
        new_user = User(
            username = username,
            email = email,
            password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()
            flash("Database error: Could not register user.", "danger")
            return redirect(url_for("signup"))
        
    return render_template("login_signup/signup.html")

@app.route("/check-username", methods=["POST"])
def check_username():
    data = request.get_json()
    username = data.get("username", "").strip()

    # Query the database for the username
    user = User.query.filter_by(username=username).first()

    return jsonify({"exists": user is not None})

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False

        # Fetch user from MySQL
        user = User.query.filter_by(username=username).first()

        # Verify user exists and check password hash
        if not user or not check_password_hash(user.password_hash, password):
            error = "Invalid username or password."
        else:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for("admin_meetings"))

    return render_template("login_signup/login.html", error=error)

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            flash("Please enter your email address.", "reset_error")
            return redirect(url_for("forgot_password"))

        user = User.query.filter_by(email=email).first()
        if user:
            reset_token = generate_reset_token(user.email)
            reset_url = url_for("reset_password", token=reset_token, _external=True)
            try:
                send_reset_email(user.email, reset_url)
            except Exception:
                flash("Email service is not configured. Please contact the administrator.", "reset_error")
                return redirect(url_for("forgot_password"))
        else:
            app.logger.warning("Password reset requested for unknown email: %s", email)

        flash("A reset link has been sent.", "success")
        return redirect(url_for("login"))

    return render_template("login_signup/forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = verify_reset_token(token, max_age=1800)
    if not email:
        flash("This reset link is invalid or has expired.", "reset_error")
        return redirect(url_for("forgot_password"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("This reset link is invalid or has expired.", "reset_error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or not confirm_password:
            flash("Please provide a new password and confirm it.", "reset_error")
            return redirect(url_for("reset_password", token=token))

        if new_password != confirm_password:
            flash("Passwords do not match.", "reset_error")
            return redirect(url_for("reset_password", token=token))

        if len(new_password) < 8:
            flash("Password must be at least 8 characters long.", "reset_error")
            return redirect(url_for("reset_password", token=token))

        user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        flash("Password reset successfully!", "success")
        return redirect(url_for("login"))

    return render_template("login_signup/reset_password.html")

@app.route("/logout")
@login_required
def logout():
    logout_user() # Clears the session cookie
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/join", methods=["GET", "POST"])
def join_meeting():
    if request.method == "POST":
        raw_code = request.form.get("voter_code") or ""
        code = raw_code.strip().upper()
        
        if not code:
            flash("Please enter a private key.", "join_error")
            return redirect(url_for('join_meeting'))

        voter = Voter.query.filter_by(code=code).first()
        
        if voter:
            session['voter_id'] = voter.id
            session['voter_name'] = voter.name
            session['voter_code'] = voter.code
            return redirect(url_for('voter_dashboard', code=voter.code))
        else:
            # Use flash and REDIRECT to prevent persistent errors on refresh
            flash("Invalid private key. Please try again.", "join_error")
            return redirect(url_for('join_meeting'))
            
    return render_template("voter/join.html")

@app.route("/voter-logout")
def voter_logout():
    session.pop('voter_id', None)
    session.pop('voter_name', None)
    session.pop('voter_code', None)
    return redirect(url_for("join_meeting"))

@app.route("/voting-systems")
def voting_systems():
    return render_template("voting_systems.html")

@app.route("/admin/meetings")
@login_required
def admin_meetings():
    # For now, just list all meetings in plain form
    meetings = Meeting.query.filter_by(admin_id=current_user.id).all()
    return render_template("admin/meetings.html", meetings=meetings)

@app.route("/admin/meetings/new", methods=["GET", "POST"])
@login_required
def create_meeting():
    if request.method == "GET":
        # Modal posts here; no standalone page needed. Redirect to admin list.
        return redirect(url_for("admin_meetings"))

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip() or None

    if not title:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {"ok": False, "error": "Title is required."}, 400

        flash("Meeting title is required.", "error")
        return redirect(url_for("admin_meetings"))

    # Create and save meeting
    new_meeting = Meeting(title=title, description=description, admin_id=current_user.id)
    db.session.add(new_meeting)
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {
            "ok": True,
            "meeting": {
                "id": new_meeting.id,
                "title": new_meeting.title,
                "description": new_meeting.description,
            },
        }

    return redirect(url_for('admin_meetings'))

@app.route("/admin/meetings/<int:meeting_id>")
@login_required
def meeting_detail(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    return render_template("admin/meeting_detail.html", meeting=meeting)

@app.route("/admin/meetings/<int:meeting_id>/delete", methods=["POST"])
@login_required
def delete_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    motion_ids = [m.id for m in meeting.motions]
    voter_ids = [v.id for v in meeting.voters]

    if motion_ids:
        Vote.query.filter(Vote.motion_id.in_(motion_ids)).delete(synchronize_session=False)
        Option.query.filter(Option.motion_id.in_(motion_ids)).delete(synchronize_session=False)
        Motion.query.filter(Motion.id.in_(motion_ids)).delete(synchronize_session=False)

    if voter_ids:
        Vote.query.filter(Vote.voter_id.in_(voter_ids)).delete(synchronize_session=False)
        Voter.query.filter(Voter.id.in_(voter_ids)).delete(synchronize_session=False)

    db.session.delete(meeting)
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {"ok": True}

    flash("Meeting deleted.", "success")
    return redirect(url_for("admin_meetings"))

@app.route("/admin/meetings/<int:meeting_id>/update", methods=["POST"])
@login_required
def update_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    # Ensure only owner can edit
    if meeting.admin_id != current_user.id:
        abort(403)

    meeting.title = request.form.get("title", "").strip()
    meeting.description = request.form.get("description", "").strip()

    if not meeting.title:
        flash("Title is required.", "danger")
        return redirect(url_for("meeting_detail", meeting_id=meeting_id))
    
    db.session.commit()
    flash("Meeting updated successfully.", "success")
    return redirect(url_for("meeting_detail", meeting_id=meeting_id))

@app.route("/admin/meetings/<int:meeting_id>/motions/new", methods=["GET", "POST"])
@login_required
def create_motion(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        motion_type = request.form.get("type")
        candidate_text = (request.form.get("candidates") or "").strip()
        num_winners_raw = (request.form.get("num_winners") or "").strip()

        if not title:
            error = {"ok": False, "error": "Motion title is required."}
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return error, 400
            flash(error["error"], "error")
            return redirect(url_for("meeting_detail", meeting_id=meeting.id))

        if motion_type not in ("YES_NO", "CANDIDATE", "PREFERENCE"):
            error = {"ok": False, "error": "Invalid motion type."}
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return error, 400
            flash(error["error"], "error")
            return redirect(url_for("meeting_detail", meeting_id=meeting.id))

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

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {
                "ok": True,
                "motion": {
                    "id": motion.id,
                    "title": motion.title,
                    "type": motion.type,
                    "num_winners": motion.num_winners,
                },
            }

        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    # GET
    return redirect(url_for("meeting_detail", meeting_id=meeting.id))

@app.route("/admin/meetings/<int:meeting_id>/voters/new", methods=["GET", "POST"])
@login_required
def create_voter(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()

        if not name:
            error = {"ok": False, "error": "Voter name is required."}
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return error, 400
            flash(error["error"], "error")
            return redirect(url_for("meeting_detail", meeting_id=meeting.id))

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

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {
                "ok": True,
                "voter": {
                    "id": voter.id,
                    "name": voter.name,
                    "code": voter.code,
                },
            }

        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    # GET -> show form
    return redirect(url_for("meeting_detail", meeting_id=meeting.id))

@app.route("/admin/meetings/<int:meeting_id>/results")
@login_required
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
@login_required
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

@app.route("/admin/voter/<int:voter_id>/update", methods=["POST"])
@login_required
def update_user(voter_id):
    """Update voter's name"""
    voter = Voter.query.get_or_404(voter_id)
    new_name = request.form.get("name")

    if not new_name or len(new_name.strip()) == 0:
        return jsonify({"error": "Voter name is required"}), 400
    
    try:
        voter.name = new_name
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error: Could not update voter"}), 500
    
@app.route("/admin/voter/<int:voter_id>/delete", methods=["POST"])
@login_required
def delete_user(voter_id):
    """Deletes a voter and their records"""
    voter = Voter.query.get_or_404(voter_id)
    
    try:
        db.session.delete(voter)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error: Could not delete voter"}), 500
    
@app.route("/admin/motion/<int:motion_id>/update", methods=["POST"])
@login_required
def update_motion(motion_id):
    """Update motion"""
    motion = Motion.query.get_or_404(motion_id)
    motion.title = request.form.get('title')
    motion.type = request.form.get('type')
    motion.num_winners = request.form.get('num_winners', type=int) or 1
    # allow updating status from the edit form
    new_status = request.form.get('status')
    if new_status:
        allowed_statuses = {"DRAFT", "PENDING", "OPEN", "CLOSED", "APPROVED", "REJECTED", "PASSED", "FAILED"}
        if new_status not in allowed_statuses:
            return jsonify({"error": "Invalid status value"}), 400
        motion.status = new_status

    if motion.type in ['CANDIDATE', 'PREFERENCE']:
        # Clear existing candidates first. Remove any votes tied to this motion
        # to avoid foreign-key constraint errors when deleting options.
        try:
            Vote.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)
        except Exception:
            # If Vote table not present or other issue, continue and let commit handle errors
            pass

        Option.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)

        raw_options = request.form.get('options', '')
        for name in [c.strip() for c in raw_options.split('\n') if c.strip()]:
            new_c = Option(text=name, motion_id=motion.id)
            db.session.add(new_c)
    
    try:
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error: Could not update motion"}), 500
    
@app.route("/admin/motion/<int:motion_id>/delete", methods=["POST"])
@login_required
def delete_motion(motion_id):
    """Deletes a motion and their records"""
    motion = Motion.query.get_or_404(motion_id)
    
    try:
        Vote.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)
        Option.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)
        db.session.delete(motion)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error: Could not delete motion"}), 500

@app.route("/update_motion_status/<int:motion_id>", methods=["POST"])
@login_required
def update_motion_status(motion_id):
    motion = Motion.query.get_or_404(motion_id)
    # Convert to uppercase to match the allowed list
    new_status = request.form.get("status", "").upper() 

    allowed_statuses = {"DRAFT", "OPEN", "CLOSED"} # Add others as needed

    if new_status in allowed_statuses:
        motion.status = new_status
        db.session.commit() # This saves it to the DB
        flash(f"Status updated to {new_status}", "success")
    else:
        flash("Invalid status selection.", "danger")
        
    # Ensure you redirect to meeting_detail so the UI updates
    return redirect(url_for("meeting_detail", meeting_id=motion.meeting_id))

@app.route("/vote/<code>")
def voter_dashboard(code):
    if session.get('voter_code') != code:
        flash("Please join the meeting with your private key first.", "join_error")
        return redirect(url_for('join_meeting'))
    
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
    if session.get('voter_code') != code:
        flash("Please join the meeting with your private key.", "join_error")
        return redirect(url_for('join_meeting'))
    
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
