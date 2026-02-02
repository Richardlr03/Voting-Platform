from flask import flash, render_template, request, send_from_directory, session, url_for
from sqlalchemy import and_

from app.extensions import db
from app.models import Meeting, Motion, Vote, Voter


def register_public_routes(app):
    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            app.static_folder,
            "Votora_Favicon.png",
            mimetype="image/png",
        )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/join", methods=["GET", "POST"])
    def join_meeting():
        if request.method == "POST":
            raw_code = request.form.get("voter_code") or ""
            code = raw_code.strip().upper()

            if not code:
                flash("Please enter a private key.", "join_error")
                return redirect(url_for("join_meeting"))

            voter = Voter.query.filter_by(code=code).first()
            if voter:
                session["voter_id"] = voter.id
                session["voter_name"] = voter.name
                session["voter_code"] = voter.code
                return redirect(url_for("voter_dashboard", code=voter.code))

            flash("Invalid private key. Please try again.", "join_error")
            return redirect(url_for("join_meeting"))

        return render_template("voter/join.html")

    @app.route("/voter-logout")
    def voter_logout():
        session.pop("voter_id", None)
        session.pop("voter_name", None)
        session.pop("voter_code", None)
        return redirect(url_for("join_meeting"))

    @app.route("/voting-systems")
    def voting_systems():
        return render_template("voting_systems.html")

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
        voted_motion_ids = {vote.motion_id for vote in voter.votes}

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
        motion = Motion.query.filter_by(id=motion_id, meeting_id=meeting.id).first_or_404()

        simple_vote = None
        preference_ranks = {}
        votes_for_motion = [vote for vote in voter.votes if vote.motion_id == motion.id]

        for vote in votes_for_motion:
            if vote.preference_rank is None:
                simple_vote = vote
            else:
                preference_ranks[vote.option_id] = vote.preference_rank

        if request.method == "POST":
            if motion.type == "PREFERENCE":
                existing_pref_votes = Vote.query.filter(
                    and_(
                        Vote.voter_id == voter.id,
                        Vote.motion_id == motion.id,
                        Vote.preference_rank.isnot(None),
                    )
                ).all()
                for existing in existing_pref_votes:
                    db.session.delete(existing)

                ranks = []
                for option in motion.options:
                    value = request.form.get(f"opt_{option.id}_rank")
                    if not value:
                        continue
                    try:
                        rank = int(value)
                    except ValueError:
                        continue
                    if rank <= 0:
                        continue
                    ranks.append((rank, option.id))

                for rank, option_id in ranks:
                    db.session.add(
                        Vote(
                            voter_id=voter.id,
                            motion_id=motion.id,
                            option_id=option_id,
                            preference_rank=rank,
                        )
                    )

            else:
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
                            db.session.add(
                                Vote(
                                    voter_id=voter.id,
                                    motion_id=motion.id,
                                    option_id=option_id_int,
                                    preference_rank=None,
                                )
                            )

            db.session.commit()
            flash("Your vote for this motion has been recorded.", "success")
            return redirect(url_for("voter_dashboard", code=voter.code))

        return render_template(
            "voter/vote_motion.html",
            invalid=False,
            voter=voter,
            meeting=meeting,
            motion=motion,
            simple_vote=simple_vote,
            preference_ranks=preference_ranks,
        )
