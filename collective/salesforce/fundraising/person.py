from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form
from dexterity.membrane.content.member import IMember
from zope.app.container.interfaces import IObjectAddedEvent

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

@grok.subscribe(IPerson, IObjectAddedEvent)
def upsertSalesforceContact(person, event):
    # abort if this site doesn't have this product installed
    mdata = getToolByName(person, 'portal_memberdata')
    if 'sf_object_id' not in mdata.propertyIds():
        return

    # Skip if the sf_object_id is already set (could happen from 
    # collective.salesforce.content sync)
    if getattr(person, 'sf_object_id', None):
        return

    # upsert Contact in Salesforce
    sfbc = getToolByName(person, 'portal_salesforcebaseconnector')
    
    res = sfbc.upsert('Email', {
        'type': 'Contact',
        'FirstName': person.first_name,
        'LastName': person.last_name,
        'Email': person.email,
        'MailingStreet': person.address,
        'MailingCity': person.city,
        'MailingState': person.state,
        'MailingPostalCode': person.zip,
        'MailingCountry': person.country,
        'Gender__c': person.gender,
        'Online_Fundraising_User__c' : True,
    })
    if not res[0]['success']:
        raise Exception(res[0]['errors'][0]['message'])

    # store the contact's Salesforce Id
    person.sf_object_id = res[0]['id']

    person.reindexObject()
