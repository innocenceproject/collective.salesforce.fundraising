from five import grok
from plone.directives import form
from z3c.form import button, field
from plone.dexterity.utils import createContentInContainer
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage
from collective.salesforce.fundraising.donor_quote import IDonorQuote

from collective.salesforce.fundraising import MessageFactory as _


class CreatePersonalCampaignPageForm(form.Form):
    grok.name('create-personal-campaign-page')
    grok.require('collective.salesforce.fundraising.AddPersonalCampaign')
    grok.context(IFundraisingCampaign)

    @property
    def fields(self):
        return field.Fields(IPersonalCampaignPage).select('title', 'goal', 'image', 'personal_appeal', 'thank_you_message')

    ignoreContext = True

    label = _(u"Create Personal Campaign Page")
    description = _(u"Set a goal and encourage your friends, family, and colleagues to donate towards your goal.")

    @button.buttonAndHandler(_(u'Create'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        # Add a personal campaign within the current context,
        # using the data from the form.
        parent_campaign = self.context
        campaign = createContentInContainer(parent_campaign,
            'collective.salesforce.fundraising.personalcampaignpage',
            checkConstraints=False, **data)

        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        contact_id = member.getProperty('sf_object_id')

        # Add the campaign in Salesforce
        # XXX Is the default status okay?
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        res = sfbc.create({
            'type': 'Campaign',
            'Type': 'Personal Fundraising',
            'ParentId': parent_campaign.sf_object_id,
            'Name': data['title'],
            'Public_Name__c': data['title'],
            'ExpectedRevenue': data['goal'],
            'Personal_Campaign_Contact__c': contact_id,
            })
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # Save the Id of the new campaign so it can be updated later.
        campaign.sf_object_id = res[0]['id']
        campaign.reindexObject(idxs=['sf_object_id'])

        # Send the user to their new campaign.
        IStatusMessage(self.request).add(u'Welcome to your personal campaign page!')
        self.request.response.redirect(campaign.absolute_url())

    @button.buttonAndHandler(_(u"Cancel"))
    def handleCancel(self, action):
        return

class CreateDonorQuote(form.Form):
    grok.name('create-donor-quote')
    grok.require('collective.salesforce.fundraising.AddDonorQuote')
    grok.context(IFundraisingCampaign)

    @property
    def fields(self):
        return field.Fields(IDonorQuote).select('quote','name','image','email')

    ignoreContext = True

    label = _(u"Tell Your Story")
    description = _(u"Tell other potential donors what moved you to donate and why they should too.")

    @button.buttonAndHandler(_(u'Submit'))
    def handleOk(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return
        
        # Add a donor quote in the current context,
        # using the data from the form
        parent_campaign = self.context
        quote = createContentInContainer(parent_campaign,
            'collective.salesforce.fundraising.donorquote',
            checkConstraints=False, **data)
        
        mtool = getToolByName(self.context, 'portal_membership')
        contact_id = None
        if not mtool.isAnonymousUser():
            member = mtool.getAuthenticatedMember()
            contact_id = member.getProperty('sf_object_id')

        # Add the Constituent Quote to Salesforce
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        res = sfbc.create({
            'type': 'Constituent_Quote__c',
            'Quote__c': data['quote'],
            'Name__c': data['name'],
            'Campaign__c': parent_campaign.sf_object_id,
            'Contact__c': contact_id,
        })

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # Save the Id of the constituent quote so it can be updated
        quote.sf_object_id = res[0]['id']
        quote.reindexObject(idxs=['sf_object_id'])

        # Send the user back to the thank you page with a note about their quote
        # Hide the donor quote section of the thank you page
        IStatusMessage(self.request).add(u'Your story has been successfully submitted.')
        self.request.response.redirect(parent_campaign.absolute_url() + '/thank-you?hide=donorquote')
