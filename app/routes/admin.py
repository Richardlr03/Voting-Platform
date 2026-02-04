from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    CandidateVote,
    Meeting,
    Motion,
    Option,
    PreferenceVote,
    Voter,
    YesNoVote,
)
from app.services.security import generate_voter_code
from app.services.voting import tally_candidate_election, tally_preference_sequential_irv


def register_admin_routes(app):
    @app.route("/admin/meetings")
    @login_required
    def admin_meetings():
        meetings = Meeting.query.filter_by(admin_id=current_user.id).all()
        return render_template("admin/meetings.html", meetings=meetings)

    @app.route("/admin/meetings/new", methods=["GET", "POST"])
    @login_required
    def create_meeting():
        if request.method == "GET":
            return redirect(url_for("admin_meetings"))

        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip() or None

        if not title:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"ok": False, "error": "Title is required."}, 400

            flash("Meeting title is required.", "error")
            return redirect(url_for("admin_meetings"))

        new_meeting = Meeting(
            title=title, description=description, admin_id=current_user.id
        )
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

        return redirect(url_for("admin_meetings"))

    @app.route("/admin/meetings/<int:meeting_id>")
    @login_required
    def meeting_detail(meeting_id):
        meeting = Meeting.query.get_or_404(meeting_id)
        return render_template("admin/meeting_detail.html", meeting=meeting)

    @app.route("/admin/meetings/<int:meeting_id>/delete", methods=["POST"])
    @login_required
    def delete_meeting(meeting_id):
        meeting = Meeting.query.get_or_404(meeting_id)

        motion_ids = [motion.id for motion in meeting.motions]
        voter_ids = [voter.id for voter in meeting.voters]

        if motion_ids:
            YesNoVote.query.filter(YesNoVote.motion_id.in_(motion_ids)).delete(
                synchronize_session=False
            )
            CandidateVote.query.filter(CandidateVote.motion_id.in_(motion_ids)).delete(
                synchronize_session=False
            )
            PreferenceVote.query.filter(PreferenceVote.motion_id.in_(motion_ids)).delete(
                synchronize_session=False
            )
            Option.query.filter(Option.motion_id.in_(motion_ids)).delete(
                synchronize_session=False
            )
            Motion.query.filter(Motion.id.in_(motion_ids)).delete(
                synchronize_session=False
            )

        if voter_ids:
            YesNoVote.query.filter(YesNoVote.voter_id.in_(voter_ids)).delete(
                synchronize_session=False
            )
            CandidateVote.query.filter(CandidateVote.voter_id.in_(voter_ids)).delete(
                synchronize_session=False
            )
            PreferenceVote.query.filter(PreferenceVote.voter_id.in_(voter_ids)).delete(
                synchronize_session=False
            )
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

            if motion_type not in ("YES_NO", "FPTP", "PREFERENCE"):
                error = {"ok": False, "error": "Invalid motion type."}
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return error, 400
                flash(error["error"], "error")
                return redirect(url_for("meeting_detail", meeting_id=meeting.id))

            num_winners = None
            if motion_type == "PREFERENCE":
                try:
                    parsed = int(num_winners_raw) if num_winners_raw else 1
                    num_winners = parsed if parsed >= 1 else 1
                except ValueError:
                    num_winners = 1

            motion = Motion(
                meeting_id=meeting.id,
                title=title,
                type=motion_type,
                status="DRAFT",
                num_winners=num_winners,
            )
            db.session.add(motion)
            db.session.flush()

            if motion_type == "YES_NO":
                for option_text in ("Yes", "No", "Abstain"):
                    db.session.add(Option(motion_id=motion.id, text=option_text))
            elif motion_type in ("FPTP", "PREFERENCE") and candidate_text:
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

            flash("Motion added successfully.", "success")
            return redirect(url_for("meeting_detail", meeting_id=meeting.id))

        flash("Motion added successfully.", "success")
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

            voter = Voter(meeting_id=meeting.id, name=name, code=generate_voter_code())
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

            flash("Voter added successfully.", "success")
            return redirect(url_for("meeting_detail", meeting_id=meeting.id))

        flash("Voter added successfully.", "success")
        return redirect(url_for("meeting_detail", meeting_id=meeting.id))

    @app.route("/admin/meetings/<int:meeting_id>/results")
    @login_required
    def meeting_results(meeting_id):
        meeting = Meeting.query.get_or_404(meeting_id)
        results = []

        for motion in meeting.motions:
            if motion.type == "PREFERENCE":
                pref_result = tally_preference_sequential_irv(motion)
                results.append(
                    {
                        "motion": motion,
                        "result_type": motion.type,
                        "pref": pref_result,
                    }
                )
                continue

            if motion.type == "FPTP":
                candidate_result = tally_candidate_election(motion)
                results.append(
                    {
                        "motion": motion,
                        "result_type": motion.type,
                        "candidate": candidate_result,
                    }
                )
                continue

            option_counts = {option.id: 0 for option in motion.options}
            for vote in motion.yes_no_votes:
                if vote.option_id in option_counts:
                    option_counts[vote.option_id] += 1

            total_votes = sum(option_counts.values())
            option_results = []
            for option in motion.options:
                count = option_counts.get(option.id, 0)
                percent = (count / total_votes * 100) if total_votes > 0 else 0
                option_results.append(
                    {"option": option, "count": count, "percent": percent}
                )

            results.append(
                {
                    "motion": motion,
                    "result_type": motion.type,
                    "simple": {
                        "total_votes": total_votes,
                        "option_results": option_results,
                    },
                }
            )

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
            voter_map = {}
            if motion.type == "PREFERENCE":
                votes_for_motion = motion.preference_votes
            elif motion.type == "FPTP":
                votes_for_motion = motion.candidate_votes
            else:
                votes_for_motion = motion.yes_no_votes

            for vote in votes_for_motion:
                voter_map.setdefault(vote.voter_id, {"voter": vote.voter, "votes": []})
                voter_map[vote.voter_id]["votes"].append(vote)

            rows = []
            for data in voter_map.values():
                voter = data["voter"]
                vote_list = data["votes"]

                if motion.type == "PREFERENCE":
                    sorted_votes = sorted(
                        vote_list,
                        key=lambda item: item.preference_rank,
                    )
                    parts = []
                    for item in sorted_votes:
                        parts.append(f"{item.preference_rank}: {item.option.text}")
                    choice_display = ", ".join(parts)
                else:
                    choice_display = ", ".join(item.option.text for item in vote_list)

                rows.append({"voter": voter, "choice_display": choice_display})

            rows.sort(key=lambda row: row["voter"].name.lower())

            motions_detail.append(
                {
                    "motion": motion,
                    "rows": rows,
                    "num_voters_voted": len(voter_map),
                    "num_possible_voters": len(meeting.voters),
                }
            )

        return render_template(
            "admin/meeting_votes.html",
            meeting=meeting,
            motions_detail=motions_detail,
        )

    @app.route("/admin/voter/<int:voter_id>/update", methods=["POST"])
    @login_required
    def update_user(voter_id):
        voter = Voter.query.get_or_404(voter_id)
        new_name = request.form.get("name")

        if not new_name or len(new_name.strip()) == 0:
            return jsonify({"error": "Voter name is required"}), 400

        try:
            voter.name = new_name
            db.session.commit()
            flash("Voter updated successfully.", "success")
            return jsonify({"success": True}), 200
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Database error: Could not update voter"}), 500

    @app.route("/admin/voter/<int:voter_id>/delete", methods=["POST"])
    @login_required
    def delete_user(voter_id):
        voter = Voter.query.get_or_404(voter_id)

        try:
            db.session.delete(voter)
            db.session.commit()
            flash("Voter deleted successfully.", "success")
            return jsonify({"success": True}), 200
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Database error: Could not delete voter"}), 500

    @app.route("/admin/motion/<int:motion_id>/update", methods=["POST"])
    @login_required
    def update_motion(motion_id):
        motion = Motion.query.get_or_404(motion_id)
        motion.title = request.form.get("title")
        motion.type = request.form.get("type")
        motion.num_winners = request.form.get("num_winners", type=int) or 1

        new_status = request.form.get("status")
        if new_status:
            allowed_statuses = {
                "DRAFT",
                "PENDING",
                "OPEN",
                "CLOSED",
                "APPROVED",
                "REJECTED",
                "PASSED",
                "FAILED",
            }
            if new_status not in allowed_statuses:
                return jsonify({"error": "Invalid status value"}), 400
            motion.status = new_status

        if motion.type in ["FPTP", "PREFERENCE"]:
            try:
                CandidateVote.query.filter_by(motion_id=motion.id).delete(
                    synchronize_session=False
                )
                PreferenceVote.query.filter_by(motion_id=motion.id).delete(
                    synchronize_session=False
                )
            except Exception:
                pass

            Option.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)

            raw_options = request.form.get("options", "")
            for name in [entry.strip() for entry in raw_options.split("\n") if entry.strip()]:
                db.session.add(Option(text=name, motion_id=motion.id))

        try:
            db.session.commit()
            flash("Motion updated successfully.", "success")
            return jsonify({"success": True}), 200
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Database error: Could not update motion"}), 500

    @app.route("/admin/motion/<int:motion_id>/delete", methods=["POST"])
    @login_required
    def delete_motion(motion_id):
        motion = Motion.query.get_or_404(motion_id)

        try:
            YesNoVote.query.filter_by(motion_id=motion.id).delete(
                synchronize_session=False
            )
            CandidateVote.query.filter_by(motion_id=motion.id).delete(
                synchronize_session=False
            )
            PreferenceVote.query.filter_by(motion_id=motion.id).delete(
                synchronize_session=False
            )
            Option.query.filter_by(motion_id=motion.id).delete(synchronize_session=False)
            db.session.delete(motion)
            db.session.commit()
            flash("Motion deleted successfully.", "success")
            return jsonify({"success": True}), 200
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Database error: Could not delete motion"}), 500

    @app.route("/update_motion_status/<int:motion_id>", methods=["POST"])
    @login_required
    def update_motion_status(motion_id):
        motion = Motion.query.get_or_404(motion_id)
        new_status = request.form.get("status", "").upper()
        allowed_statuses = {"DRAFT", "OPEN", "CLOSED"}

        if new_status in allowed_statuses:
            motion.status = new_status
            db.session.commit()
            flash(f"Status updated to {new_status}", "success")
        else:
            flash("Invalid status selection.", "danger")

        return redirect(url_for("meeting_detail", meeting_id=motion.meeting_id))
