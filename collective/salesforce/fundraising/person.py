from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form
from dexterity.membrane.content.member import IMember
from zope.app.container.interfaces import IObjectAddedEvent
from zope.lifecycleevent.interfaces import IObjectModifiedEvent
from collective.salesforce.content.interfaces import IModifiedViaSalesforceSync

from plone.namedfile.interfaces import IImageScaleTraversable

# Interface class; used to define content-type schema.

class IPerson(form.Schema, IImageScaleTraversable, IMember):
    """
    A person who is a user in Plone and a Contact in Salesforce
    """

    form.model("models/person.xml")

alsoProvides(IPerson, IContentType)

class Person(dexterity.Item):
    grok.implements(IPerson)

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

