from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
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

    # e.g. "YES_NO" or "CANDIDATE"
    type = db.Column(db.String(50), nullable=False, default="YES_NO")

    # e.g. "DRAFT", "OPEN", "CLOSED"
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
        candidate_text = request.form.get("candidates")  # may be empty

        # Create the motion
        motion = Motion(
            meeting_id=meeting.id,
            title=title,
            type=motion_type,
            status="DRAFT",  # we can change to OPEN/CLOSED later
        )
        db.session.add(motion)
        db.session.flush()  # get motion.id before creating options

        # Create options based on motion type
        if motion_type == "YES_NO":
            default_options = ["Yes", "No", "Abstain"]
            for opt in default_options:
                db.session.add(Option(motion_id=motion.id, text=opt))
        elif motion_type == "CANDIDATE":
            # Split candidate text by lines (ignore empty lines)
            if candidate_text:
                lines = [line.strip() for line in candidate_text.splitlines() if line.strip()]
                for name in lines:
                    db.session.add(Option(motion_id=motion.id, text=name))

        db.session.commit()

        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    # GET → show form
    return render_template("admin/create_motion.html", meeting=meeting)

if __name__ == "__main__":
    app.run(debug=True)