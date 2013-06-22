from five import grok
from zope.component import getUtility
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFCore.utils import getToolByName
from zope.component.hooks import getSite
from collective.simplesalesforce.utils import ISalesforceUtility
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
        sfconn = getUtility(ISalesforceUtility).get_connection()
        first, last = split_name(member.getProperty('fullname'))
        email = member.getProperty('email')

        res = sfconn.query("select id from contact where email = '%s' order by LastModifiedDate desc" % email)
        contact_id = None
        if res['totalSize'] > 0:
            contact_id = res['records'][0]['id']

        res = sfconn.Contact.upsert(contact_id, {
            'FirstName': first,
            'LastName': last,
            'Email': email,
        })
        if not res['success']:
            raise Exception(res['errors'][0])

        # store the contact's Salesforce Id
        member.setMemberProperties({'sf_object_id': res['id']})
