from five import grok
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFCore.utils import getToolByName
from zope.site.hooks import getSite
from collective.salesforce.fundraising.interfaces import IMemberCreated


def split_name(name):
    """Try to split a full name into first and last names.

    Currently it splits on spaces and counts the last word as the last name,
    unless the penultimate word starts with a lowercase letter (e.g. 'van Dyk'),
    in which case the penultimate word is included in the last name.

    We'll see if this is good enough.
    """
    parts = [part for part in name.strip().split(' ') if part]
    if len(parts) <= 1:
        return '', name
    try:
        if parts[-2][0].islower():
            return ' '.join(parts[:-2]), ' '.join(parts[-2:])
        return ' '.join(parts[:-1]), parts[-1]
    except IndexError:
        return '', ''


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
