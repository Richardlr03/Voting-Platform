from app.extensions import db


class PreferenceVote(db.Model):
    __tablename__ = "preference_votes"

    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey("voters.id"), nullable=False)
    motion_id = db.Column(db.Integer, db.ForeignKey("motions.id"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("options.id"), nullable=False)
    preference_rank = db.Column(db.Integer, nullable=False)
