from datetime import datetime

import uuid
import structlog

from flask import Blueprint, jsonify, request, g

from conditional.models.models import CurrentCoops
from conditional.models.models import CommitteeMeeting
from conditional.models.models import FreshmanCommitteeAttendance
from conditional.models.models import MemberCommitteeAttendance
from conditional.models.models import TechnicalSeminar
from conditional.models.models import FreshmanSeminarAttendance
from conditional.models.models import MemberSeminarAttendance
from conditional.models.models import HouseMeeting
from conditional.models.models import FreshmanHouseMeetingAttendance
from conditional.models.models import MemberHouseMeetingAttendance
from conditional.models.models import FreshmanAccount

from conditional.util.flask import render_template
from conditional.util.auth import restrict_eboard, restrict_evals

from conditional import db, auth, ldap

logger = structlog.get_logger()

attendance_bp = Blueprint('attendance_bp', __name__)


def get_name(m):
    return m['cn'][0].decode('utf-8')


@attendance_bp.route('/attendance/ts_members')
@auth.oidc_auth
@restrict_eboard
def get_all_members():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='retrieve technical seminar attendance list')

    members = ldap.get_current_students()

    named_members = [
        {
            'display': f.name,
            'value': f.id,
            'freshman': True
        } for f in FreshmanAccount.query.filter(
            FreshmanAccount.eval_date > datetime.now())]

    for m in members:
        uid = m['uid'][0].decode('utf-8')
        name = "{name} ({uid})".format(name=get_name(m), uid=uid)

        named_members.append(
            {
                'display': name,
                'value': uid,
                'freshman': False
            })

    return jsonify({'members': named_members}), 200


@attendance_bp.route('/attendance/hm_members')
@auth.oidc_auth
@restrict_evals
def get_non_alumni_non_coop(internal=False):
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='retrieve house meeting attendance list')

    # Only Members Who Have Paid Dues Are Required to
    # go to house meetings
    non_alumni_members = ldap.get_active_members()
    coop_members = [u.username for u in CurrentCoops.query.all()]

    named_members = [
        {
            'display': f.name,
            'value': f.id,
            'freshman': True
        } for f in FreshmanAccount.query.filter(
            FreshmanAccount.eval_date > datetime.now())]

    for m in non_alumni_members:
        uid = m['uid'][0].decode('utf-8')

        if uid in coop_members:
            continue
        name = "{name} ({uid})".format(name=get_name(m), uid=uid)

        named_members.append(
            {
                'display': name,
                'value': uid,
                'freshman': False
            })

    if internal:
        return named_members
    else:
        return jsonify({'members': named_members}), 200


@attendance_bp.route('/attendance/cm_members')
@auth.oidc_auth
@restrict_eboard
def get_non_alumni():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='retrieve committee meeting attendance list')

    non_alumni_members = ldap.get_current_students()

    named_members = [
        {
            'display': f.name,
            'value': f.id,
            'freshman': True
        } for f in FreshmanAccount.query.filter(
            FreshmanAccount.eval_date > datetime.now())]
    for m in non_alumni_members:
        uid = m['uid'][0].decode('utf-8')
        name = "{name} ({uid})".format(name=get_name(m), uid=uid)

        named_members.append(
            {
                'display': name,
                'value': uid,
                'freshman': False
            })

    return jsonify({'members': named_members}), 200


@attendance_bp.route('/attendance_cm')
@auth.oidc_auth
@restrict_eboard
def display_attendance_cm():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('frontend', action='display committee meeting attendance page')

    return render_template('attendance_cm.html',
                           date=datetime.now().strftime("%Y-%m-%d"))


@attendance_bp.route('/attendance_ts')
@auth.oidc_auth
@restrict_eboard
def display_attendance_ts():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('frontend', action='display technical seminar attendance page')

    return render_template('attendance_ts.html',
                           date=datetime.now().strftime("%Y-%m-%d"))


@attendance_bp.route('/attendance_hm')
@auth.oidc_auth
@restrict_evals
def display_attendance_hm():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('frontend', action='display house meeting attendance page')

    return render_template('attendance_hm.html',
                           date=datetime.now().strftime("%Y-%m-%d"),
                           members=get_non_alumni_non_coop(internal=True))


@attendance_bp.route('/attendance/submit/cm', methods=['POST'])
@auth.oidc_auth
@restrict_eboard
def submit_committee_attendance():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='submit committee meeting attendance')

    post_data = request.get_json()

    committee = post_data['committee']
    m_attendees = post_data['members']
    f_attendees = post_data['freshmen']
    timestamp = post_data['timestamp']

    timestamp = datetime.strptime(timestamp, "%Y-%m-%d")
    meeting = CommitteeMeeting(committee, timestamp)

    db.session.add(meeting)
    db.session.flush()
    db.session.refresh(meeting)

    for m in m_attendees:
        logger.info('backend',
                    action=("gave attendance to %s for %s" % (m, committee))
                    )
        db.session.add(MemberCommitteeAttendance(m, meeting.id))

    for f in f_attendees:
        logger.info('backend',
                    action=("gave attendance to freshman-%s for %s" % (f, committee))
                    )
        db.session.add(FreshmanCommitteeAttendance(f, meeting.id))

    db.session.commit()
    return jsonify({"success": True}), 200


@attendance_bp.route('/attendance/submit/ts', methods=['POST'])
@auth.oidc_auth
@restrict_eboard
def submit_seminar_attendance():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4())
                     )
    log.info('api', action='submit technical seminar attendance')

    post_data = request.get_json()

    seminar_name = post_data['name']
    m_attendees = post_data['members']
    f_attendees = post_data['freshmen']
    timestamp = post_data['timestamp']

    timestamp = datetime.strptime(timestamp, "%Y-%m-%d")
    seminar = TechnicalSeminar(seminar_name, timestamp)

    db.session.add(seminar)
    db.session.flush()
    db.session.refresh(seminar)

    for m in m_attendees:
        logger.info('backend',
                    action=("gave attendance to %s for %s" % (m, seminar_name))
                    )
        db.session.add(MemberSeminarAttendance(m, seminar.id))

    for f in f_attendees:
        logger.info('backend',
                    action=("gave attendance to freshman-%s for %s" % (f, seminar_name))
                    )
        db.session.add(FreshmanSeminarAttendance(f, seminar.id))

    db.session.commit()
    return jsonify({"success": True}), 200


@attendance_bp.route('/attendance/submit/hm', methods=['POST'])
@auth.oidc_auth
@restrict_evals
def submit_house_attendance():
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='submit house meeting attendance')

    # status: Attended | Excused | Absent

    post_data = request.get_json()

    timestamp = datetime.strptime(post_data['timestamp'], "%Y-%m-%d")

    meeting = HouseMeeting(timestamp)

    db.session.add(meeting)
    db.session.flush()
    db.session.refresh(meeting)

    if "members" in post_data:
        for m in post_data['members']:
            logger.info('backend',
                        action=(
                            "gave %s to %s for %s house meeting" % (
                                m['status'], m['uid'], timestamp.strftime("%Y-%m-%d")))
                        )
            db.session.add(MemberHouseMeetingAttendance(
                m['uid'],
                meeting.id,
                None,
                m['status']))

    if "freshmen" in post_data:
        for f in post_data['freshmen']:
            logger.info('backend',
                        action=("gave %s to freshman-%s for %s house meeting" % (
                            f['status'], f['id'], timestamp.strftime("%Y-%m-%d")))
                        )
            db.session.add(FreshmanHouseMeetingAttendance(
                f['id'],
                meeting.id,
                None,
                f['status']))

    db.session.commit()
    return jsonify({"success": True}), 200


@attendance_bp.route('/attendance/alter/hm/<uid>/<hid>', methods=['GET'])
@auth.oidc_auth
@restrict_evals
def alter_house_attendance(uid, hid):
    if not uid.isdigit():
        member_meeting = MemberHouseMeetingAttendance.query.filter(
            MemberHouseMeetingAttendance.uid == uid,
            MemberHouseMeetingAttendance.meeting_id == hid
        ).first()
        member_meeting.attendance_status = "Attended"
        db.session.commit()
        return jsonify({"success": True}), 200
    else:
        freshman_meeting = FreshmanHouseMeetingAttendance.query.filter(
            FreshmanHouseMeetingAttendance.fid == uid,
            FreshmanHouseMeetingAttendance.meeting_id == hid
        ).first()

        freshman_meeting.attendance_status = "Attended"
        db.session.commit()
        return jsonify({"success": True}), 200


@attendance_bp.route('/attendance/alter/hm/<uid>/<hid>', methods=['POST'])
@auth.oidc_auth
@restrict_evals
def alter_house_excuse(uid, hid):
    log = logger.new(user_id=g.userinfo['uuid'],
                     request_id=str(uuid.uuid4()))
    log.info('api', action='edit house meeting excuse')

    post_data = request.get_json()
    hm_status = post_data['status']
    hm_excuse = post_data['excuse']

    logger.info('backend', action="edit hm %s status: %s excuse: %s" %
                                  (hid, hm_status, hm_excuse))

    if not uid.isdigit():
        MemberHouseMeetingAttendance.query.filter(
            MemberHouseMeetingAttendance.uid == uid,
            MemberHouseMeetingAttendance.meeting_id == hid
        ).update({
            'excuse': hm_excuse,
            'attendance_status': hm_status
        })
    else:
        FreshmanHouseMeetingAttendance.query.filter(
            FreshmanHouseMeetingAttendance.fid == uid,
            FreshmanHouseMeetingAttendance.meeting_id == hid
        ).update({
            'excuse': hm_excuse,
            'attendance_status': hm_status
        })

    db.session.flush()
    db.session.commit()
    return jsonify({"success": True}), 200
