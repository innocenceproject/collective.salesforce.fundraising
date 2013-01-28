from urllib import quote
from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.interface import invariant
from zope.interface import Invalid
from zope.component import getUtility
from AccessControl.SecurityManagement import newSecurityManager
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form
from dexterity.membrane.content.member import IMember, IEmail
from dexterity.membrane.membrane_helpers import get_brains_for_email
from zope.app.container.interfaces import IObjectAddedEvent
from zope.lifecycleevent.interfaces import IObjectModifiedEvent
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.namedfile.field import NamedBlobImage
from Products.CMFCore.interfaces import ISiteRoot

from collective.salesforce.content.interfaces import IModifiedViaSalesforceSync
from collective.salesforce.fundraising import MessageFactory as _


class IPerson(form.Schema, IImageScaleTraversable, IMember):
    """
    A person who is a user in Plone and a Contact in Salesforce
    """

    portrait = NamedBlobImage(
            title = u"Portrait",
            description = u"The photo used to identify you on the site",
            required = False,
    )

    form.model("models/person.xml")

alsoProvides(IPerson, IContentType)

class IAddPerson(form.Schema, IEmail):
    """
    Add Interface for a Person with limited fields
    NOTE: This seems to be the only way to get a custom edit form with limited
    fields since we're using the model xml for most fields
    """
    
    first_name = schema.TextLine(
        title=_(u"First Name"),
    )
    last_name = schema.TextLine(
        title=_(u"Last Name"),
    )
    email_opt_in = schema.Bool(
        title=_(u"Join our Email List?"),
        description=_(u"Check this box to receive occassional updates via email"),
        required=False,
        default=True,
    )
    password = schema.Password(
        title=_(u"Password"),
    )
    password_confirm = schema.Password(
        title=_(u"Confirm Password"),
    )

    came_from = schema.TextLine(
        title=_(u"Redirect after create"),
        required=False,
    )

    form.mode(came_from='hidden')

    @invariant
    def passwordsInvariant(data):
        if data.password != data.password_confirm:
            raise Invalid(_(u"Your passwords do not match, please enter the same password in both fields"))

class Person(dexterity.Item):
    grok.implements(IAddPerson, IPerson)

    def upsertToSalesforce(self):
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
       
        # only upsert values that are non-empty to Salesforce to avoid overwritting existing values with null 
        data = {
            'type': 'Contact',
            'FirstName': self.first_name,
            'LastName': self.last_name,
            'Email': self.email,
            'Online_Fundraising_User__c' : True,
        }
        if self.email_opt_in:
            data['Email_Opt_In__c'] = self.email_opt_in
        if self.phone:
            data['HomePhone'] = self.phone
        if self.address:
            data['MailingStreet'] = self.address
        if self.city:
            data['MailingCity'] = self.city
        if self.state:
            data['MailingState'] = self.state
        if self.zip:
            data['MailingPostalCode'] = self.zip
        if self.country:
            data['MailingCountry'] = self.country
        if self.gender:
            data['Gender__c'] = self.gender

        res = sfbc.upsert('Email', data)

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # store the contact's Salesforce Id if it doesn't already have one
        if not getattr(self, 'sf_object_id', None):
            self.sf_object_id = res[0]['id']
    
        self.reindexObject()

        return res


@grok.subscribe(IPerson, IObjectAddedEvent)
def setOwnerRole(person, event):
    roles = list(person.get_local_roles_for_userid(person.email))

    if IModifiedViaSalesforceSync.providedBy(event):
        return

    if 'Owner' not in roles:
        roles.append('Owner')
        person.manage_setLocalRoles(person.email, roles)


@grok.subscribe(IPerson, IObjectAddedEvent)
def upsertNewSalesforceContact(person, event):
    # abort if this site doesn't have this product installed
    mdata = getToolByName(person, 'portal_memberdata')
    if 'sf_object_id' not in mdata.propertyIds():
        return

    # NOTE: commented out because we always want to update SF when a contact is updated
    # Skip if the sf_object_id is already set (could happen from 
    # collective.salesforce.content sync)
    #if getattr(person, 'sf_object_id', None):
    #    return

    # upsert Contact in Salesforce
    person.upsertToSalesforce()


@grok.subscribe(IPerson, IObjectModifiedEvent)
def upsertModifiedSalesforceContact(person, event):
    # abort if this site doesn't have this product installed
    mdata = getToolByName(person, 'portal_memberdata')
    if 'sf_object_id' not in mdata.propertyIds():
        return

    # upsert Contact in Salesforce
    person.upsertToSalesforce()


class EmailLoginRouter(grok.View):
    grok.name('email-login-redirect')
    grok.context(ISiteRoot)

    def render(self):
        came_from = self.request.form.get('came_from',None)
        came_from_arg = ''
        if came_from:
            came_from_arg = '&came_from=%s' % quote(came_from)
        email = self.request.form.get('email',None)
        if not email:
            return self.request.response.redirect(self.context.absolute_url() + '/login' + came_from_arg)
   
        category = self.get_user_category(email)
        if category == None:
            return self.request.response.redirect(self.context.absolute_url() + '/create-user-account?email=' + quote(email) + came_from_arg)
        if category == 'registered':
            # redirect to login
            # FIXME: This code assumes the login portlet is the second tab on the pluggable login page.  I'm sure there's a better way to do this.
            return self.request.response.redirect(self.context.absolute_url() + '/login?tab=1&email=' + quote(email) + came_from_arg)
        if category == 'social' or category == 'donor_only':
            return self.request.response.redirect(self.context.absolute_url() + '/set-password-form?email=' + quote(email) + came_from_arg)
        
    def get_user_category(self, email):
        """ Returns either registered, social, donor_only, or None """
        res = get_brains_for_email(self.context, email)
        if not res:
            return None

        mtool = getToolByName(self.context, 'portal_membership')
        acl = getToolByName(self.context, 'acl_users')
        newSecurityManager(None, acl.getUser(email))
        mtool.loginUser()

        category = 'donor_only'

        person = res[0].getObject()

        if person.social_signin:
            category = 'social'

        if person.registered:
            category = 'registered'

        mtool.logoutUser()

        return category

   
class CleanupSalesforceIds(grok.View):
    grok.name('cleanup-salesforce-person-ids')
    grok.require('cmf.ModifyPortalContent')
    grok.context(ISiteRoot) 

    def render(self):
        
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
    
        soql = "select Id, Email from Contact where Online_Fundraising_User__c = True"
      
        # FIXME: Handle paginated query in case the number of contacts is > 200 
        res = sfbc.query(soql)

        num_person_updated = 0
        num_member_updated = 0
        num_skipped = 0

        mtool = getToolByName(self.context, 'portal_membership')

        for contact in res:
            person_res = get_brains_for_email(self.context, contact.Email)
            if not person_res:
                num_skipped += 1
                continue
            person = person_res[0].getObject()
            if person.sf_object_id != contact.Id:
                num_person_updated += 1
                person.sf_object_id = contact.Id
                person.reindexObject(idxs=['sf_object_id'])
           
            member = mtool.getMemberById(person.email)
            if not member:
                continue
            if member.getProperty('sf_object_id') != person.sf_object_id:
                num_member_updated = 0
                member.setMemberProperties({'sf_object_id': person.sf_object_id})

        return "Updated %s Person objects, %s Member objects, and skipped %s non-existing Contacts" % (num_person_updated, num_member_updated, num_skipped)
