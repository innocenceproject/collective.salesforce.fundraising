from five import grok
from zope.component.hooks import getSite
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleVocabulary
from Products.CMFCore.utils import getToolByName
from plone.uuid.interfaces import IUUID

class ThankYouTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.thank_you_templates(context)
        
    def thank_you_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IThankYouEmail':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(ThankYouTemplates, name=u'collective.salesforce.fundraising.thank_you_templates')

class HonoraryTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.honorary_templates(context)
        
    def honorary_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IHonoraryEmail':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(HonoraryTemplates, name=u'collective.salesforce.fundraising.honorary_templates')

class MemorialTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.memorial_templates(context)
        
    def memorial_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IMemorialEmail':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(MemorialTemplates, name=u'collective.salesforce.fundraising.memorial_templates')

class PersonalPageCreatedTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.personal_page_created_templates(context)
        
    def personal_page_created_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IPersonalPageCreated':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(PersonalPageCreatedTemplates, name=u'collective.salesforce.fundraising.personal_page_created_templates')

class PersonalPageDonationTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.personal_page_donation_templates(context)
        
    def personal_page_donation_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IPersonalPageDonation':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(PersonalPageDonationTemplates, name=u'collective.salesforce.fundraising.personal_page_donation_templates')

class RecurringReceiptTemplates(object):
    grok.implements(IVocabularyFactory)

    def __call__(self, context):
        return self.recurring_receipt_templates(context)
        
    def recurring_receipt_templates(self, context):
        query = { "portal_type" : "collective.chimpdrill.template" }
        terms = []
        pc = getToolByName(getSite(), 'portal_catalog')
        res = pc.searchResults(**query)
        for template in res:
            obj = template.getObject()
            uuid = IUUID(obj)
            if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IRecurringReceipt':
                terms.append(SimpleVocabulary.createTerm(uuid, uuid, obj.title))
        return SimpleVocabulary(terms)

grok.global_utility(RecurringReceiptTemplates, name=u'collective.salesforce.fundraising.recurring_receipt_templates')

