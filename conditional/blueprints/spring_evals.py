import uuid
import structlog

from flask import Blueprint, g

from conditional.models.models import MemberCommitteeAttendance
from conditional.models.models import MemberHouseMeetingAttendance
from conditional.models.models import MajorProject
from conditional.models.models import HouseMeeting
from conditional.models.models import SpringEval
from conditional.models.models import HousingEvalsSubmission

from conditional.util.flask import render_template

from conditional import db, auth, ldap

spring_evals_bp = Blueprint('spring_evals_bp', __name__)

logger = structlog.get_logger()


@spring_evals_bp.route('/spring_evals/')
@auth.oidc_auth
def display_spring_evals(internal=False):
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('frontend', action='display membership evaluations listing')

    def get_cm_count(member_id):
        return len([a for a in MemberCommitteeAttendance.query.filter(
            MemberCommitteeAttendance.uid == member_id)])

    # TODO FIXME XXX: Replace this line and update the logic below when models have UUIDs
    # members = [m['entryUUID'][0].decode('utf-8') for m in ldap.get_active_members()]
    members = ldap.get_active_members()

    sp_members = []
    for member in members:
        uid = member['uid'][0].decode('utf-8')
        member_uuid = member['entryUUID'][0].decode('utf-8')

        spring_entry = SpringEval.query.filter(
            SpringEval.uid == uid and
            SpringEval.active).first()

        if spring_entry is None:
            spring_entry = SpringEval(uid)
            db.session.add(spring_entry)
            db.session.flush()
            db.session.commit()
            # something bad happened to get here
            print("User did not have existing spring eval data")

        eval_data = None
        if internal:
            eval_data = HousingEvalsSubmission.query.filter(
                HousingEvalsSubmission.uid == uid).first()

            if HousingEvalsSubmission.query.filter(HousingEvalsSubmission.uid == uid).count() > 0:
                eval_data = \
                    {
                        'social_attended': eval_data.social_attended,
                        'social_hosted': eval_data.social_hosted,
                        'seminars_attended': eval_data.technical_attended,
                        'seminars_hosted': eval_data.technical_hosted,
                        'projects': eval_data.projects,
                        'comments': eval_data.comments
                    }
        h_meetings = [m.meeting_id for m in
                      MemberHouseMeetingAttendance.query.filter(
                          MemberHouseMeetingAttendance.uid == uid
                      ).filter(
                          MemberHouseMeetingAttendance.attendance_status == "Absent"
                      )]
        member = {
            'name': ldap.get_name(member_uuid),
            'uid': uid,
            'status': spring_entry.status,
            'committee_meetings': get_cm_count(uid),
            'house_meetings_missed':
                [
                    {
                        "date": m.date.strftime("%Y-%m-%d"),
                        "reason":
                            MemberHouseMeetingAttendance.query.filter(
                                MemberHouseMeetingAttendance.uid == uid).filter(
                                MemberHouseMeetingAttendance.meeting_id == m.id).first().excuse
                    }
                    for m in HouseMeeting.query.filter(
                    HouseMeeting.id.in_(h_meetings)
                )
                    ],
            'major_projects': [
                {
                    'name': p.name,
                    'status': p.status,
                    'description': p.description
                } for p in MajorProject.query.filter(
                    MajorProject.uid == uid)]
        }
        member['major_projects_len'] = len(member['major_projects'])
        member['major_project_passed'] = False
        for mp in member['major_projects']:
            if mp['status'] == "Passed":
                member['major_project_passed'] = True
                break

        if internal:
            member['housing_evals'] = eval_data
        sp_members.append(member)

    sp_members.sort(key=lambda x: x['committee_meetings'], reverse=True)
    sp_members.sort(key=lambda x: len(x['house_meetings_missed']))
    sp_members.sort(key=lambda x: len([p for p in x['major_projects'] if p['status'] == "Passed"]), reverse=True)
    # return names in 'first last (username)' format
    if internal:
        return sp_members
    else:
        return render_template('spring_evals.html',
                               members=sp_members)
