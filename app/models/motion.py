from app.extensions import db


class Motion(db.Model):
    __tablename__ = "motions"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False, default="YES_NO")
    num_winners = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT")

    options = db.relationship("Option", backref="motion", lazy=True)
    yes_no_votes = db.relationship("YesNoVote", backref="motion", lazy=True)
    candidate_votes = db.relationship("CandidateVote", backref="motion", lazy=True)
    preference_votes = db.relationship("PreferenceVote", backref="motion", lazy=True)
