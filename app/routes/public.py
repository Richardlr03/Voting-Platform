from flask import flash, redirect, render_template, request, send_from_directory, session, url_for

from app.extensions import db
from app.models import CandidateVote, Motion, PreferenceVote, ScoreVote, Voter, YesNoVote


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
        voted_motion_ids = {
            *{vote.motion_id for vote in voter.yes_no_votes},
            *{vote.motion_id for vote in voter.candidate_votes},
            *{vote.motion_id for vote in voter.preference_votes},
            *{vote.motion_id for vote in voter.score_votes},
        }

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
                score_values=None,
            )

        meeting = voter.meeting
        motion = Motion.query.filter_by(id=motion_id, meeting_id=meeting.id).first_or_404()

        simple_vote = None
        preference_ranks = {}
        score_values = {}
        if motion.type == "PREFERENCE":
            votes_for_motion = [
                vote for vote in voter.preference_votes if vote.motion_id == motion.id
            ]
            for vote in votes_for_motion:
                preference_ranks[vote.option_id] = vote.preference_rank
        elif motion.type == "FPTP":
            simple_vote = next(
                (vote for vote in voter.candidate_votes if vote.motion_id == motion.id),
                None,
            )
        elif motion.type == "SCORE":
            votes_for_motion = [
                vote for vote in voter.score_votes if vote.motion_id == motion.id
            ]
            for vote in votes_for_motion:
                score_values[vote.option_id] = vote.score
        else:
            simple_vote = next(
                (vote for vote in voter.yes_no_votes if vote.motion_id == motion.id),
                None,
            )

        if request.method == "POST":
            if motion.type == "PREFERENCE":
                existing_pref_votes = PreferenceVote.query.filter_by(
                    voter_id=voter.id, motion_id=motion.id
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
                        PreferenceVote(
                            voter_id=voter.id,
                            motion_id=motion.id,
                            option_id=option_id,
                            preference_rank=rank,
                        )
                    )
            elif motion.type == "SCORE":
                existing_score_votes = ScoreVote.query.filter_by(
                    voter_id=voter.id, motion_id=motion.id
                ).all()
                for existing in existing_score_votes:
                    db.session.delete(existing)

                for option in motion.options:
                    value = request.form.get(f"opt_{option.id}_score")
                    if value is None or value == "":
                        continue
                    try:
                        score_value = round(float(value), 1)
                    except ValueError:
                        continue
                    if score_value < 0:
                        continue
                    if motion.score_max is not None and score_value > motion.score_max:
                        score_value = float(motion.score_max)

                    db.session.add(
                        ScoreVote(
                            voter_id=voter.id,
                            motion_id=motion.id,
                            option_id=option.id,
                            score=score_value,
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
                        vote_model = CandidateVote if motion.type == "FPTP" else YesNoVote
                        if simple_vote is None:
                            simple_vote = vote_model.query.filter_by(
                                voter_id=voter.id, motion_id=motion.id
                            ).first()
                        if simple_vote:
                            simple_vote.option_id = option_id_int
                        else:
                            db.session.add(
                                vote_model(
                                    voter_id=voter.id,
                                    motion_id=motion.id,
                                    option_id=option_id_int,
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
            score_values=score_values,
        )
