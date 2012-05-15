from five import grok
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite
from collective.salesforce.fundraising.interfaces import IMemberCreated
from collective.salesforce.fundraising.nameparser import HumanName


def split_name(fullname):
    """Try to split a full name into first and last names.
    """

    name = HumanName(fullname)
    first = getattr(name, 'first', None)
    middle = getattr(name, 'middle', None)
    last = getattr(name, 'last', None)
    suffix = getattr(name, 'suffix', None)

    # Combine first with middle
    if middle:
        first = first + ' ' + middle

    # Combine last with suffix
    if suffix:
        last = last + ' ' + suffix

    return first, last


@grok.subscribe(IMemberCreated)
def handleNewAccount(event):
    site = getSite()
    mtool = getToolByName(site, 'portal_membership')
    # only do this for self-registering users,
    # not ones added by a Manager
    if mtool.isAnonymousUser():
        member = event.member

        # abort if this site doesn't have this product installed
        mdata = getToolByName(site, 'portal_memberdata')
        if 'sf_object_id' not in mdata.propertyIds():
            return

        # log them in immediately
        newSecurityManager(None, member.getUser())
        mtool.loginUser()

        # create Contact in Salesforce
        sfbc = getToolByName(site, 'portal_salesforcebaseconnector')
        first, last = split_name(member.getProperty('fullname'))
        email = member.getProperty('email')
        res = sfbc.upsert('Email', {
            'type': 'Contact',
            'FirstName': first,
            'LastName': last,
            'Email': email,
        })
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # store the contact's Salesforce Id
        member.setMemberProperties({'sf_object_id': res[0]['id']})
