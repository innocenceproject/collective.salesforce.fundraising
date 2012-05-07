from five import grok
from plone.directives import form
from z3c.form import button, field
from plone.dexterity.utils import createContentInContainer
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage

from collective.salesforce.fundraising import MessageFactory as _


class CreatePersonalCampaignPageForm(form.Form):
    grok.name('create-personal-campaign-page')
    grok.require('collective.salesforce.fundraising.AddPersonalCampaign')
    grok.context(IFundraisingCampaign)

    @property
    def fields(self):
        return field.Fields(IPersonalCampaignPage).select('title', 'personal_appeal', 'goal')

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

        # Add the campaign in Salesforce
        # XXX Should include id of Contact for current user
        # XXX Is the default status okay?
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        res = sfbc.create({
            'type': 'Campaign',
            'Type': 'Personal Fundraising',
            'ParentId': parent_campaign.sf_object_id,
            'Name': data['title'],
            'Public_Name__c': data['title'],
            'ExpectedRevenue': data['goal'],
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
