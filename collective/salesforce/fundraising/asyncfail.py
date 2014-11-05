
from plone.app.async.service import _executeAsUser
from twisted.python.failure import Failure
import logging
import zc.async

log = logging.getLogger(__name__)


msg = """From: 
<tal:root define="lt string:&lt;;
                  gt string:&gt;;
                  dummy python:request.RESPONSE.setHeader('Content-Type', 'text/plain;; charset=%s' % options['charset']);
                  member python:options['member'];"
>From: "<span tal:replace="python:here.email_from_name" />" <span tal:replace="structure lt"/><span tal:replace="python:here.email_from_address" /><span tal:replace="structure gt"/>
To: <span tal:replace="python:member.getProperty('email')" />
Subject: <span i18n:domain="yourproduct" i18n:translate="yoursubjectline" tal:omit-tag="">Subject Line</span>
Content-Type: text/plain; charset=<span tal:replace="python:options['charset']" />
Dear <span tal:replace="member/getFullname" />:
You can now log in as <span tal:replace="member/getId" /> at <span tal:replace="python:options['portal_url']" />
Cheers!
The website team
</tal:root>
"""


def email_failure(event):
    """Send an email about an async job failure.

    ``event`` provides ``plone.app.async.interfaces.IJobFailure``.
    event.object is usually a ``twisted.python.failure.Failure``.
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
            "j._callable_root is %r, but was expecting %r. "
            "Original traceback:\n%s", j._callable_root, _executeAsUser, tb)
        return

    j.setUp()
    try:
        context_path, portal_path, uf_path, user_id = j.args[:4]
        _executeAsUser(
            context_path, portal_path, uf_path, user_id,
            email_failure_in_context, tb)
    except:
        log.exception(
            '_executeAsUser() failed. Original traceback:\n%s', tb)
    finally:
        j.tearDown()


def email_failure_in_context(context, tb):
    try:
        host = getToolByName(self, 'MailHost')
        # The ``immediate`` parameter causes an email to be sent immediately
        # (if any error is raised) rather than sent at the transaction
        # boundary or queued for later delivery.
        return host.send(mail_text, immediate=True)
    except SMTPRecipientsRefused:
        # Don't disclose email address on failure
        raise SMTPRecipientsRefused('Recipient address rejected by server')