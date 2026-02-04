from app.extensions import db


class Option(db.Model):
    __tablename__ = "options"

    id = db.Column(db.Integer, primary_key=True)
    motion_id = db.Column(db.Integer, db.ForeignKey("motions.id"), nullable=False)
    text = db.Column(db.String(200), nullable=False)

    yes_no_votes = db.relationship("YesNoVote", backref="option", lazy=True)
    candidate_votes = db.relationship("CandidateVote", backref="option", lazy=True)
    preference_votes = db.relationship("PreferenceVote", backref="option", lazy=True)
