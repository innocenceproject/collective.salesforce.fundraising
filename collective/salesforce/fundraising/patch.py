# PAS raises PrincipalCreated event before the new user has its properties set.
# So we patch the registration form to raise a similar event at a better time.

from zope.event import notify
from Products.CMFCore.utils import getToolByName
from plone.app.users.browser.register import RegistrationForm
from collective.salesforce.fundraising.interfaces import MemberCreated
from zope.interface import Interface

orig_handle_join_success = RegistrationForm.handle_join_success


def handle_join_success(self, data):
    res = orig_handle_join_success(self, data)
    mtool = getToolByName(self.context, 'portal_membership')
    member = mtool.getMemberById(data['username'])
    notify(MemberCreated(member))
    return res
RegistrationForm.handle_join_success = handle_join_success


# The plone.directives.form.schema.Schema interface is gone, but some
# catalogs continue to depend on it.  Provide a stub so databases don't
# break.  Refs #912.


try:
    from plone.directives.form.schema import Schema
except ImportError:
    from plone.directives.form import schema

    class Schema(Interface):
        """BBB stub"""

    schema.Schema = Schema
