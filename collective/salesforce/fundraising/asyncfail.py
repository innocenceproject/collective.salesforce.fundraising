
"""Send a notification when an async job fails."""

from email.utils import formataddr
import datetime
import logging
import os
import socket
import thread

from AccessControl.SecurityManagement import noSecurityManager
from plone.app.async.service import _executeAsUser
from Products.CMFCore.utils import getToolByName
from twisted.python.failure import Failure
import zc.async
import Zope2

from collective.salesforce.fundraising.utils import get_settings

try:
    # plone < 4.3
    from zope.app.component.hooks import setSite
except:
    from zope.component.hooks import setSite

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


def email_failure(event):
    """Send an email about an async job failure.

    This is a subscriber to ``plone.app.async.interfaces.IJobFailure`` events.
    event.object is usually a ``zc.twist.Failure``, a subclass of
    ``twisted.python.failure.Failure``.
    """
    if isinstance(event.object, Failure):
        tb = event.object.getTraceback()
    else:
        tb = repr(event.object)

    # HACK: At the moment, no Plone context is available, even globally,
    # because job.tearDown() was called after the failure.  Get the
    # original job from zc.async.local.job.parent.parent, use that job
    # to build the context, and call email_failure_in_context().
    # If any part of this hack fails, try to log the reason.

    j1 = getattr(zc.async.local, 'job', None)
    j0 = getattr(j1, 'parent', None)
    j = getattr(j0, 'parent', None)
    if j is None:
        log.error(
            "Unable to send the failure email because "
            "zc.async.local.job.parent.parent doesn't exist. "
            "Original traceback:\n%s", tb)
        return

    if j._callable_root != _executeAsUser:
        log.error(
            "Unable to send the failure email because "
            "j._callable_root is %r, but asyncfail.py expected %r. "
            "Original traceback:\n%s", j._callable_root, _executeAsUser, tb)
        return

    try:
        context_path, portal_path, uf_path, user_id, func = j.args[:5]

        try:
            func_name = '%s:%s' % (func.__module__, func.__name__)
        except Exception:
            func_name = repr(func)

        info = {
            'func_name': func_name,
            'func': repr(func),
            'args': repr(j.args[5:]),
            'kwargs': repr(j.kwargs),
            'portal_path': repr(portal_path),
            'context_path': repr(context_path),
            'userfolder_path': repr(uf_path),
            'user_id': repr(user_id),
            'tb': tb,
        }
    except Exception:
        log.exception(
            "Unable to send the failure email.  Original traceback:\n%s", tb)
        return

    setup_info = j.setUp()
    try:
        execute_in_portal(
            portal_path,
            email_failure_from_portal,
            info=info)
    except Exception:
        log.exception(
            'email_failure_from_portal() failed. Original traceback:\n%s', tb)
        return
    finally:
        j.tearDown(setup_info)


def execute_in_portal(portal_path, func, info):
    """Reconstruct environment and execute func.

    This is similar to _executeAsUser but doesn't bother with the context
    or the security manager, since they could cause unrelated errors.
    """
    transaction = Zope2.zpublisher_transactions_manager  # Supports isDoomed
    transaction.begin()
    app = Zope2.app()
    result = None
    try:
        try:
            portal = app.unrestrictedTraverse(portal_path, None)
            if portal is None:
                raise ValueError(
                    'Portal path %s not found' % '/'.join(portal_path))
            setSite(portal)

            result = func(portal, info)
            transaction.commit()

        except Exception:
            transaction.abort()
            raise
    finally:
        noSecurityManager()
        setSite(None)
        app._p_jar.close()
    return result


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
