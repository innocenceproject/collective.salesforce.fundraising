import copy

from zope import schema
from zope.component import getMultiAdapter
from zope.interface import Interface

from five import grok
from plone.directives import form
from z3c.form import button, field
from plone.directives import dexterity
from plone.dexterity.utils import createContentInContainer
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.fundraising_campaign import IHideDonationForm
from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage
from collective.salesforce.fundraising.personal_campaign_page import IEditPersonalCampaignPage
from collective.salesforce.fundraising.donor_quote import IDonorQuote

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import send_confirmation_email


class CreatePersonalCampaignPageForm(form.Form):
    grok.name('create-personal-campaign-page')
    #grok.require('collective.salesforce.fundraising.AddPersonalCampaign')
    grok.context(IFundraisingCampaign)
    grok.implements(IHideDonationForm)

    @property
    def fields(self):
        fields = field.Fields(IPersonalCampaignPage).select('title', 'description', 'image', 'goal', 'personal_appeal', 'thank_you_message')
        image_field = copy.copy(fields['image'].field)
        image_field.required = True
        fields['image'].field = image_field
        return fields

    ignoreContext = True

    label = _(u"Create Personal Campaign Page")
    description = _(u"Set a goal and encourage your friends, family, and colleagues to donate towards your goal.")

    def update(self):
        super(CreatePersonalCampaignPageForm, self).update()
        existing_personal_campaign = self.context.get_personal_fundraising_campaign_url()
        if existing_personal_campaign:
            messages = IStatusMessage(self.request)
            messages.add("You can't create more than one personal page per campaign.")
            self.request.response.redirect(self.context.absolute_url())

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

        settings = get_settings()

        # Add the campaign in Salesforce
        sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
        data = {
            'type': 'Campaign',
            'Type': 'Personal Fundraising',
            'ParentId': parent_campaign.sf_object_id,
            'Name': data['title'],
            'Description': data['description'],
            'Public_Name__c': data['title'],
            'ExpectedRevenue': data['goal'],
            'Personal_Campaign_Contact__c': contact_id,
            'IsActive': True,
            'Status': 'In Progress',
            }
        if settings.sf_campaign_record_type_personal:
            data['RecordTypeID'] = settings.sf_campaign_record_type_personal

        res = sfbc.create(data)
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # Save the Id of the new campaign so it can be updated later.
        campaign.parent_sf_id = parent_campaign.sf_object_id
        campaign.sf_object_id = res[0]['id']
        campaign.reindexObject(idxs=['sf_object_id'])

        # Send email confirmation and links.
        data['parent'] = parent_campaign
        data['campaign'] = campaign
        data['FirstName'] = member.getProperty('fullname', 'friend')
        email_view = getMultiAdapter((campaign, self.request), name='page-confirmation-email')
        email_view.set_page_values(data)
        email_body = email_view()
        email_to = member.getProperty('email')
        subject = 'New Personal Campaign Page Created'
        send_confirmation_email(campaign, subject, email_to, email_body)

        # Send the user to their new campaign.
        IStatusMessage(self.request).add(u'Welcome to your personal campaign page!')
        self.request.response.redirect(campaign.absolute_url())

    @button.buttonAndHandler(_(u"Cancel"))
    def handleCancel(self, action):
        return

class EditPersonalCampaign(dexterity.EditForm):
    grok.name('edit-personal-campaign')
    grok.require('collective.salesforce.fundraising.EditPersonalCampaign')
    grok.context(IPersonalCampaignPage)

    label = _(u"Edit My Fundraising Page")
    description = _(u"Use the form below to edit your fundraising page to create the most effective appeal to your friends and family.")
    schema = IEditPersonalCampaignPage

#    @button.buttonAndHandler(_(u"Save Changes"))
#    def handleSaveChanges(self, action):
#        data, errors = self.extractData()
#        if errors:
#            self.status = self.formErrorsMessage
#            return
#
#
#        settings = get_settings()
#
#        changed = False
#        if data['title'] != self.context.Title():
#            changed = True
#        if data['description'] != self.context.Description():
#            changed = True
#        if data['goal'] != self.context.goal:
#            changed = True
#
#        if changed:
#            # Update the campaign in Salesforce
#            sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
#            data = {
#                'type': 'Campaign',
#                'id': self.context.sf_object_id,
#                'Name': data['title'],
#                'Description': data['description'],
#                'Public_Name__c': data['title'],
#                'ExpectedRevenue': data['goal'],
#                }
#
#            res = sfbc.update(data)
#            if not res[0]['success']:
#                raise Exception(res[0]['errors'][0]['message'])
#
#        campaign.reindexObject()
#
#        # Send the user to their new campaign.
#        IStatusMessage(self.request).add(u'Your changes have been saved.  You can see your changes below.!')
#        self.request.response.redirect(self.context.absolute_url())
#        return
#
#    @button.buttonAndHandler(_(u"Cancel"))
#    def handleCancel(self, action):
#        return


class CreateDonorQuote(form.Form):
    grok.name('create-donor-quote')
    grok.require('collective.salesforce.fundraising.AddDonorQuote')
    grok.context(IFundraisingCampaign)
    grok.implements(IHideDonationForm)

    @property
    def fields(self):
        return field.Fields(IDonorQuote).select('quote','name','image','contact_sf_id', 'donation_id', 'amount')

    ignoreContext = True

    label = _(u"Testimonial")
    description = _(u"Provide a quote to inspire others to give.")

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
            'Contact__c': data['contact_sf_id'],
            'Opportunity__c': data['donation_id'],
            'Amount__c': data['amount'],
        })

        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])

        # Save the Id of the constituent quote so it can be updated
        quote.sf_object_id = res[0]['id']
        quote.parent_sf_id = parent_campaign.sf_object_id
        quote.reindexObject(idxs=['sf_object_id'])

        # Send the user back to the thank you page with a note about their quote
        # Hide the donor quote section of the thank you page
        IStatusMessage(self.request).add(u'Your story has been successfully submitted.')
        if data['donation_id'] and data['amount']:
            self.request.response.redirect(parent_campaign.absolute_url() + '/thank-you?hide=donorquote&donation_id=%s&amount=%s' % (data['donation_id'], data['amount']))
        else:
            self.request.response.redirect(parent_campaign.absolute_url() + '/thank-you?hide=donorquote')
