"""Send a notification when an async job fails."""

from email.utils import formataddr
import datetime
import logging
import os
import socket
import thread

from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising.utils import get_settings

log = logging.getLogger(__name__)


msg_template = u"""\
From: {from_formatted}
To: {to_formatted}
Content-Type: text/plain; charset="utf-8"
Subject: Async error in {func_name}

An error occurred in a job managed by plone.app.async.
This error was reported by {mymod}.

func_name: {func_name}
function: {func}
args: {args}
kwargs: {kwargs}
portal_path: {portal_path}
context_path: {context_path}
userfolder_path: {userfolder_path}
user_id: {user_id}
hostname: {hostname}
pid: {pid}
thread_id: {thread_id}
datetime_utc: {datetime_utc}
datetime_local: {datetime_local}

The traceback follows.

{tb}
"""


def email_failure_from_portal(portal, info):
    from_name = portal.getProperty('email_from_name')
    from_address = portal.getProperty('email_from_address')
    from_formatted = formataddr((from_name, from_address))

    settings = get_settings()
    to_address = settings.async_error_email

    all_info = info.copy()
    all_info.update({
        'from_formatted': from_formatted,
        'to_formatted': to_address,
        'hostname': socket.gethostname(),
        'pid': os.getpid(),
        'thread_id': thread.get_ident(),
        'datetime_utc': datetime.datetime.utcnow().isoformat(),
        'datetime_local': datetime.datetime.now().isoformat(),
        'mymod': __name__,
    })

    msg = msg_template.format(**all_info).encode('utf-8')

    # The ``immediate`` parameter causes an email to be sent immediately
    # (if any error is raised) rather than sent at the transaction
    # boundary or queued for later delivery.
    mh = getToolByName(portal, 'MailHost')
    mh.send(msg, immediate=True)
