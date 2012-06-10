import locale
import random
import smtplib
import uuid
from datetime import date

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility
from zope.component import getMultiAdapter

from zope.interface import Interface
from zope.interface import alsoProvides
from zope import schema
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent

from plone.z3cform.interfaces import IWrappedForm

from plone.app.textfield import RichText
from plone.namedfile import NamedBlobImage
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.memoize import instance

from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.statusmessages.interfaces import IStatusMessage

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import sanitize_soql

from collective.oembed.interfaces import IConsumer

# Interface class; used to define content-type schema.

class IFundraisingCampaign(form.Schema, IImageScaleTraversable):
    """
    A Fundraising Campaign linked to a Campaign in Salesforce.com
    """
    body = RichText(
        title=u"Fundraising Pitch",
        description=u"The body of the pitch for this campaign shown above the donation form",
    )

    thank_you_message = RichText(
        title=u"Thank You Message",
        description=u"This is the message displayed to a donor after they have donated.",
    )

    default_personal_appeal = RichText(
        title=u"Default Personal Appeal",
        description=u"When someone creates a personal campaign, this text is the default value in the Personal Appeal field.  The user can choose to keep the default or edit it.",
    )

    default_personal_thank_you = RichText(
        title=u"Default Personal Thank You Message",
        description=u"When someone creates a personal campaign, this text is the default value in the Thank You Message field.  The user can choose to keep the default or edit it.",
    )

    donation_form_tabs = schema.List(
        title=u"Donation Form Tabs",
        description=u"Enter the view names for each tab you wish to display with this form.  You can provide a friendly name for the tab by using the format VIEWNAME|LABEL",
        value_type=schema.TextLine(),
    )

    form.model("models/fundraising_campaign.xml")

alsoProvides(IFundraisingCampaign, IContentType)

class IFundraisingCampaignPage(Interface):
    """ Marker interface for campaigns that act like a fundraising campaign """

class IHideDonationForm(Interface):
    """ Marker interface for views where the donation form viewlet should not be shown """

@form.default_value(field=IFundraisingCampaign['thank_you_message'])
def thankYouDefaultValue(data):
    return get_settings().default_thank_you_message

@form.default_value(field=IFundraisingCampaign['default_personal_appeal'])
def defaultPersonalAppealDefaultValue(data):
    return get_settings().default_personal_appeal

@form.default_value(field=IFundraisingCampaign['default_personal_thank_you'])
def defaultPersonalThankYouDefaultValue(data):
    return get_settings().default_personal_thank_you_message

@form.default_value(field=IFundraisingCampaign['donation_form_tabs'])
def defaultDonationFormTabsValue(data):
    return get_settings().default_donation_form_tabs

@grok.subscribe(IFundraisingCampaign, IObjectAddedEvent)
def handleFundraisingCampaignCreated(campaign, event):
    # This is necessary because collective.salesforce.content never loads the
    # form and thus never loads the default values on creation
    if not campaign.thank_you_message:
        campaign.thank_you_message = thankYouDefaultValue(None)
    if not campaign.default_personal_appeal:
        campaign.default_personal_appeal = defaultPersonalAppealDefaultValue(None)
    if not campaign.default_personal_thank_you:
        campaign.default_personal_thank_you = defaultPersonalThankYouDefaultValue(None)
    if not campaign.donation_form_tabs:
        campaign.donation_form_tabs = defaultDonationFormTabsValue(None)

    # Add campaign in Salesforce if it doesn't have a Salesforce id yet
    if getattr(campaign, 'sf_object_id', None) is None:
        sfbc = getToolByName(campaign, 'portal_salesforcebaseconnector')

        settings = get_settings()

        # Only parse the dates if they have a value
        start_date = campaign.date_start
        if start_date:
            start_date = start_date.isoformat()
        end_date = campaign.date_end
        if end_date:
            end_date = end_date.isoformat()

        data = {
            'type': 'Campaign',
            'Type': 'Fundraising',
            'Name': campaign.title,
            'Public_Name__c': campaign.title,
            'Description': campaign.description,
            'Status': campaign.status,
            'ExpectedRevenue': campaign.goal,
            'Allow_Personal__c': campaign.allow_personal,
            'StartDate': start_date,
            'EndDate': end_date,
        }
        if settings.sf_campaign_record_type:
            data['RecordTypeId'] = settings.sf_campaign_record_type

        res = sfbc.create(data)
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])
        campaign.sf_object_id = res[0]['id']
        campaign.reindexObject(idxs=['sf_object_id'])


class FundraisingCampaignPage(object):
    def get_percent_goal(self):
        if self.goal and self.donations_total:
            return int((self.donations_total * 100) / self.goal)
        return 0

    def get_percent_timeline(self):
        if self.date_start and self.date_end:
            today = date.today()
            if self.date_end < today:
                return 100
            if self.date_start > today:
                return 0

            delta_range = self.date_end - self.date_start
            delta_current = today - self.date_start
            return int((delta_current.days * 100) / delta_range.days)
        return 0

    def get_days_remaining(self):
        if self.date_end:
            today = date.today()
            delta = self.date_end - today
            return delta.days

    def get_goal_remaining(self):
        if self.goal:
            if not self.donations_total:
                return self.goal
            return self.goal - self.donations_total

    def get_source_campaign(self):
        source_campaign = self.REQUEST.get('source_campaign', '')
        if not source_campaign:
            source_campaign = self.REQUEST.get('collective.salesforce.fundraising.source_campaign', '')
        return source_campaign

    def get_source_url(self):
        # Check if there is a cookie that captures the referrer of first entry for the session
        source_url = self.REQUEST.get('collective.salesforce.fundraising.source_url', None)
        if source_url:
            return source_url
        # If not, use the current request's HTTP_REFERER
        referrer = self.REQUEST.get('HTTP_REFERER', '')
        if referrer:
            return referrer

        # If all else fails, return the campaign's url
        return self.absolute_url()

    def populate_form_embed(self):
        form_embed = getattr(self, 'form_embed', None)
        if not form_embed:
            form_embed = get_settings().default_form_embed

        form_embed = form_embed.replace('{{CAMPAIGN_ID}}', getattr(self, 'sf_object_id', ''))
        form_embed = form_embed.replace('{{SOURCE_CAMPAIGN}}', self.get_source_campaign())
        form_embed = form_embed.replace('{{SOURCE_URL}}', self.get_source_url())
        return form_embed

    def can_create_donor_quote(self):
        # FIXME: make sure the donor just donated (check session) and that they don't already have a quote for this campaign
        return True

    def show_employer_matching(self):
        return False

    def add_donation(self, amount):
        """ Accepts an amount and adds the amount to the donations_total for this
            campaign and the parent campaign if this is a child campaign.  Also increments
            the donations_count by 1 for this campaign and the parent (if applicable).

            This should be considered temporary as the real amount will be synced periodically
            from salesforce via collective.salesforce.content.
        """
        if amount:
            amount = int(amount)
            if self.donations_total:
                self.donations_total = self.donations_total + amount
            else:
                self.donations_total = amount

            if self.direct_donations_total:
                self.direct_donations_total = self.direct_donations_total + amount
            else:
                self.direct_donations_total = amount

            if self.donations_count:
                self.donations_count = self.donations_count + 1
            else:
                self.donations_count = 1

            if self.direct_donations_count:
                self.direct_donations_count = self.direct_donations_count + 1
            else:
                self.direct_donations_count = 1

            # If this is a child campaign and its parent campaign is the parent
            # in Plone, add the value to the parent's donations_total
            if hasattr(self, 'parent_sf_id'):
                parent = self.aq_parent
                if parent.sf_object_id == self.parent_sf_id:
                    parent.donations_total = parent.donations_total + amount
                    parent.donations_count = parent.donations_count + 1

    def get_external_media_oembed(self):
        external_media = getattr(self.context, 'external_media_url', None)
        if external_media:
            consumer = getUtility(IConsumer)
            # FIXME - don't hard code maxwidth
            return consumer.get_data(self.external_media_url, maxwidth=270).get('html')
           
    def clear_donation_from_cache(self, donation_id, amount):
        """ Clears a donation from the cache.  This is useful if its value needs to be refreshed
            on the next time it's called but you don't want to call it now. """
        key = ('lookup_donation', (self, donation_id, amount), frozenset([]))
        if self._memojito_.has_key(key):
            del self._memojito_[key]
 
    @instance.memoize
    def lookup_donation(self, donation_id, amount):
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
        return sfbc.query(RECEIPT_SOQL % (donation_id, amount, self.sf_object_id))


class FundraisingCampaign(dexterity.Container, FundraisingCampaignPage):
    grok.implements(IFundraisingCampaign, IFundraisingCampaignPage)

    def get_parent_sfid(self):
        return self.sf_object_id

    def get_fundraising_campaign(self):
        """ Returns the fundraising campaign object.  Useful for subobjects to easily lookup the parent campaign """
        return self

    def personal_fundraisers_count(self):
        """ Returns the number of personal campaign pages created off this campaign """
        return len(self.listFolderContents(contentFilter = {'portal_type': 'collective.salesforce.fundraising.personalcampaignpage'}))

    def create_personal_campaign_page_link(self):
        return self.absolute_url() + '/@@create-or-view-personal-campaign'

    def can_create_personal_campaign_page(self):
        # FIXME: add logic here to check for campaign status.  Only allow if the campaign is active
        return self.allow_personal

    def get_personal_fundraising_campaign_url(self):
        """ Return the current user's personal fundraising campaign, if they already have one. """
        mtool = getToolByName(self, 'portal_membership')
        if mtool.isAnonymousUser():
            return

        member = mtool.getAuthenticatedMember()
        catalog = getToolByName(self, 'portal_catalog')
        res = catalog.searchResults(
            portal_type = 'collective.salesforce.fundraising.personalcampaignpage', 
            path = '/'.join(self.getPhysicalPath()),
            Creator = member.getId()
        )
        if res:
            return res[0].getURL()

class CampaignView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

    def addcommas(self, number):
        locale.setlocale(locale.LC_ALL, '')
        return locale.format('%d', number, 1)

    def update(self):
        # Set a cookie with referrer as source_url if no cookie has yet been set for the session
        source_url = self.request.get('collective.salesforce.fundraising.source_url', None)
        if not source_url:
            referrer = self.request.get_header('referrer')
            if referrer:
                self.request.response.setCookie('collective.salesforce.fundraising.source_url', referrer)

        # Set a cookie with the source code if it was passed in the request
        self.source_campaign = self.request.get('source_campaign', None)
        if self.source_campaign:
            self.request.response.setCookie('collective.salesforce.fundraising.source_campaign', self.source_campaign)

        tabs = []
        if self.context.donation_form_tabs:
            for tab in self.context.donation_form_tabs:
                parts = tab.split('|')
                if len(parts) == 1:
                    label = parts[0]
                else:
                    label = parts[1]
                view_name = parts[0]
           
                html = self.context.unrestrictedTraverse([view_name,])
                tabs.append({
                    'id': view_name,
                    'label': label,
                    'html': html,
                })
        self.donation_form_tabs = tabs

        # Handle form validation errors from 3rd party (right now only Authorize.net)
        # by receiving the error codes and looking up their text
        self.error = self.request.form.get('error', None)
        self.response_code = self.request.form.get('response_code',None)
        self.reason_code = self.request.form.get('reason_code', None)

        self.ssl_seal = get_settings().ssl_seal

class ThankYouView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('thank-you')
    grok.template('thank-you')

    def update(self):
        # Fetch some values that should have been passed from the redirector
        self.donation_id = self.request.form.get('donation_id', None)
        self.amount = self.request.form.get('amount', None)

        self.receipt_view = None
        self.receipt = None
        if self.donation_id and self.amount:
            self.amount = int(self.amount)
            self.receipt_view
            self.receipt_view = getMultiAdapter((self.context, self.request), name='donation-receipt')
            self.receipt = self.receipt_view()

            # Check if send_mail=true was passed and if so, send the receipt email
            if self.request.form.get('send_receipt_email', None) == 'true':
                settings = get_settings() 

                # Construct the email bodies
                pt = getToolByName(self.context, 'portal_transforms')
                email_body = getMultiAdapter((self.context, self.request), name='thank-you-email')()
                txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

                # Determine to and from addresses
                portal_url = getToolByName(self.context, 'portal_url')
                portal = portal_url.getPortalObject()
                mail_from = portal.getProperty('email_from_address')
                mail_to = self.receipt_view.contact.Email

                # Construct the email message                
                msg = MIMEMultipart('alternative')
                msg['Subject'] = settings.thank_you_email_subject
                msg['From'] = mail_from
                msg['To'] = mail_to
                part1 = MIMEText(txt_body, 'plain')
                part2 = MIMEText(email_body, 'html')
    
                msg.attach(part1)
                msg.attach(part2)

                # Attempt to send it
                try:
                    host = getToolByName(self, 'MailHost')
                    # The `immediate` parameter causes an email to be sent immediately
                    # (if any error is raised) rather than sent at the transaction
                    # boundary or queued for later delivery.
                    host.send(msg, immediate=True)

                    # Commented out in favor of passing send_receipt_email=true to the thank you view to avoid a Salesforce API call
                    # Mark the receipt as sent in Salesforce
                    #sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
                    #sfbc.update({
                        #'type': 'Opportunity',
                        #'Id': self.donation_id,
                        #'Email_Receipt_Sent__c': True,
                    #})

                except smtplib.SMTPRecipientsRefused:
                    # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
                    pass

        # Create a wrapped form for inline rendering
        from collective.salesforce.fundraising.forms import CreateDonorQuote
        if self.context.can_create_donor_quote():
            self.donor_quote_form = CreateDonorQuote(self.context, self.request)
            alsoProvides(self.donor_quote_form, IWrappedForm)

        # Determine any sections that should be collapsed
        self.hide = self.request.form.get('hide', [])
        if self.hide:
            self.hide = self.hide.split(',')

    def render_janrain_share(self):
        amount_str = ''
        if self.amount:
            amount_str = _(u' $%s' % self.amount)
        comment = _(u'I just donated%s to a great cause.  You should join me.') % amount_str

        return "rpxShareButton(jQuery('#share-message-thank-you'), 'Tell your friends you donated', '%s', '%s', '%s', '%s', '%s')" % (
            self.context.description,
            self.context.absolute_url(),
            self.context.title,
            comment,
            self.context.absolute_url() + '/@@images/image',
        )

class HonoraryMemorialView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('honorary-memorial-donation')

    form_template = ViewPageTemplateFile('fundraising_campaign_templates/honorary-memorial-donation.pt')

    def render(self):
        # Fetch some values that should have been passed from the redirector
        self.donation_id = self.request.form['donation_id']
        self.amount = int(self.request.form['amount'])

        self.receipt_view = None
        self.receipt = None
        if self.donation_id and self.amount:
            self.receipt_view = getMultiAdapter((self.context, self.request), name='donation-receipt')
            self.receipt = self.receipt_view()

            # Handle POST
            if self.request['REQUEST_METHOD'] == 'POST':
                # Fetch values from the request
                honorary_name = self.request.form.get('honorary_name', None)
                honorary_email = self.request.form.get('honorary_email', None)
                honorary_recipient = self.request.form.get('honorary_recipient', None)
                honorary_message = self.request.form.get('honorary_message', None)
                honorary_send = self.request.form.get('honorary_send', None) == 'Yes'
                honorary_type = self.request.form.get('honorary_type', None)

                # Dump the data into Salesforce
                sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
                sfbc.update({
                    'type': 'Opportunity',
                    'Id': self.donation_id,
                    'Honorary_Name__c': honorary_name,
                    'Honorary_Email__c': honorary_email,
                    'Honorary_Recipient__c': honorary_recipient,
                    'Honorary_Message__c': honorary_message,
                    'Honorary_Type__c': honorary_type,
                })

                # Expire the donation in the cache so the new Honorary values are looked up next time
                self.context.clear_donation_from_cache(self.donation_id, self.amount)

                # If there was an email passed and we're supposed to send an email, send the email
                if honorary_send and honorary_email:

                    settings = get_settings() 

                    # Construct the email bodies
                    pt = getToolByName(self.context, 'portal_transforms')
                    if honorary_type == u'Honorary':
                        email_view = getMultiAdapter((self.context, self.request), name='honorary-email')
                        email_view.set_honorary_info(
                            donor = '%(FirstName)s %(LastName)s' % self.receipt_view.contact,
                            honorary_name = honorary_name,
                            honorary_recipient = honorary_recipient,
                            honorary_email = honorary_email,
                            honorary_message = honorary_message,
                        )
                        email_body = email_view()

                    else:
                        email_view = getMultiAdapter((self.context, self.request), name='memorial-email')
                        email_view.set_honorary_info(
                            donor = '%(FirstName)s %(LastName)s' % self.receipt_view.contact,
                            honorary_name = honorary_name,
                            honorary_recipient = honorary_recipient,
                            honorary_email = honorary_email,
                            honorary_message = honorary_message,
                        )
                        email_body = email_view()
        
                    txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

                    # Construct the email message                
                    portal_url = getToolByName(self.context, 'portal_url')
                    portal = portal_url.getPortalObject()

                    mail_from = portal.getProperty('email_from_address')
                    mail_cc = self.receipt_view.contact.Email

                    msg = MIMEMultipart('alternative')
                    if honorary_type == 'Memorial': 
                        msg['Subject'] = 'Gift received in memory of %s' % honorary_name
                    else:
                        msg['Subject'] = 'Gift received in honor of %s' % honorary_name
                    msg['From'] = mail_from
                    msg['To'] = honorary_email
                    msg['Cc'] = mail_cc
        
                    part1 = MIMEText(txt_body, 'plain')
                    part2 = MIMEText(email_body, 'html')
    
                    msg.attach(part1)
                    msg.attach(part2)

                    # Attempt to send it
                    try:

                        # Send the notification email
                        host = getToolByName(self, 'MailHost')
                        host.send(msg, immediate=True)

                    except smtplib.SMTPRecipientsRefused:
                        # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
                        pass

                # Redirect on to the thank you page
                self.request.response.redirect('%s/thank-you?donation_id=%s&amount=%i&send_receipt_email=true' % (self.context.absolute_url(), self.donation_id, self.amount))


        return self.form_template()

class ShareView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    grok.implements(IHideDonationForm)
    
    grok.name('share-campaign')
    grok.template('share-campaign')


    def update(self):
        # Get all the messages in the current context
        self.messages = []
        res = self.context.listFolderContents(contentFilter = {
            'portal_type': 'collective.salesforce.fundraising.sharemessage'
        })

        # If there are less than 3 messages found, check if this is a child campaign
        if len(res) < 3:
            if hasattr(self.context, 'parent_sf_id'):
                # Add parent messages until a total of 3 messages are selected
                parent_res = self.context.__parent__.listFolderContents(contentFilter = {
                    'portal_type': 'collective.salesforce.fundraising.sharemessage'
                })
                if len(parent_res) + len(res) > 3:
                    res = res + random.sample(parent_res, 3 - len(res))
                elif len(parent_res) + len(res) <= 3:
                    res = res + parent_res
        # If there are more than 3 messages are found, select 3 at random from the list
        if len(res) > 3:
            res = random.sample(res, 3)

        self.messages = res

class CreateOrViewPersonalCampaignView(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('collective.salesforce.fundraising.AddPersonalCampaign')

    grok.name('create-or-view-personal-campaign')
    
    def render(self):
        mt = getToolByName(self.context, 'portal_membership')
        create_url = self.context.absolute_url() + '/@@create-personal-campaign-page'

        existing_campaign_url = self.context.get_personal_fundraising_campaign_url()
        if existing_campaign_url:
            return self.request.RESPONSE.redirect(existing_campaign_url)

        # If not, redirect them to the create form
        return self.request.RESPONSE.redirect(create_url)


class PersonalCampaignPagesList(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('zope2.View')
    grok.implements(IHideDonationForm)
    
    grok.name('personal-fundraisers')
    grok.template('personal-fundraisers')

    def update(self):
        # fetch the list
        pc = getToolByName(self.context, 'portal_catalog')
        query = {
            'portal_type': 'collective.salesforce.fundraising.personalcampaignpage', 
            'path': '/'.join(self.context.getPhysicalPath()),
        }
        query['sort_on'] = self.request.get('sort_on', 'donations_total')
        query['sort_order'] = 'descending'
        self.campaigns = pc.searchResults(**query) 

RECEIPT_SOQL = """select 

    Opportunity.Name, 
    Opportunity.Amount, 
    Opportunity.CloseDate, 
    Opportunity.StageName, 
    Opportunity.Honorary_Type__c, 
    Opportunity.Honorary_Name__c, 
    Opportunity.Honorary_Recipient__c, 
    Opportunity.Honorary_Email__c, 
    Opportunity.Honorary_Message__c, 
    Contact.FirstName, 
    Contact.LastName, 
    Contact.Email, 
    Contact.Phone,
    Contact.MailingStreet, 
    Contact.MailingCity,
    Contact.MailingState, 
    Contact.MailingPostalCode, 
    Contact.MailingCountry 

    from OpportunityContactRole

    where
        IsPrimary = true
        and OpportunityId = '%s'
        and Opportunity.Amount = %d
        and Opportunity.CampaignId = '%s'
"""

class DonationReceipt(grok.View):
    """ Looks up an opportunity in Salesforce and prepares a donation receipt.  Uses amount and id as keys """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation-receipt')
    grok.template('donation-receipt')

    def update(self):
        donation_id = sanitize_soql(self.request.form.get('donation_id'))
        amount = int(self.request.form.get('amount'))
        refresh = self.request.form.get('refresh') == 'true'
        res = self.context.lookup_donation(donation_id, amount)
        
        if not len(res['records']):
            raise ValueError('Donation with id %s and amount %s was not found.' % (donation_id, amount))

        settings = get_settings()
        self.organization_name = settings.organization_name
        self.donation_receipt_legal = settings.donation_receipt_legal

        self.donation = res['records'][0].Opportunity
        self.contact = res['records'][0].Contact


        
        
    
class ThankYouEmail(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('thank-you-email')
    grok.template('thank-you-email')
    
    def update(self):
        self.receipt_view = getMultiAdapter((self.context, self.request), name='donation-receipt')
        self.receipt = self.receipt_view()
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer

class HonoraryEmail(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('honorary-email')
    grok.template('honorary-email')
    
    def update(self):
        if self.request.get('show_template', None) == 'true':
            # Enable rendering of the template without honorary info
            self.set_honorary_info(
                donor = '<YOUR NAME>',
                honorary_name = '<NAME IN HONOR OF>',
                honorary_recipient = '<RECIPIENT NAME>',
                honorary_email = None,
                honorary_message = '<YOUR MESSAGE HERE (optional)>'
            )
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.request['amount']
        
    def set_honorary_info(self, donor, honorary_name, honorary_recipient, honorary_email, honorary_message):
        self.donor = donor
        self.honorary_name = honorary_name
        self.honorary_recipient = honorary_recipient
        self.honorary_email = honorary_email

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')
        try:
            self.honorary_message = pt.convertTo('text/html', honorary_message, mimetype='text/-x-web-intelligent')
        except:
            self.honorary_message = honorary_message


#FIXME: I tried to use subclasses to build these 2 views but grok seemed to be getting in the way.
# I tried making a base mixin class then 2 different views base of it and grok.View as well as 
# making MemorialEmail subclass Honorary with a new name and template.  Neither worked so I'm 
# left duplicating logic for now.
class MemorialEmail(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('memorial-email')
    grok.template('memorial-email')

    def update(self):
        if self.request.get('show_template', None) == 'true':
            # Enable rendering of the template without honorary info
            self.set_honorary_info(
                donor = '<YOUR NAME>',
                honorary_name = '<NAME IN MEMORY OF>',
                honorary_recipient = '<RECIPIENT NAME>',
                honorary_email = None,
                honorary_message = '<YOUR MESSAGE HERE (optional)>'
            )
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.request.form['amount']
        
    def set_honorary_info(self, donor, honorary_name, honorary_recipient, honorary_email, honorary_message):
        self.donor = donor
        self.honorary_name = honorary_name
        self.honorary_recipient = honorary_recipient
        self.honorary_email = honorary_email

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')
        self.honorary_message = pt.convertTo('text/html', honorary_message, mimetype='text/-x-web-intelligent')

        try:
            self.honorary_message = pt.convertTo('text/html', honorary_message, mimetype='text/-x-web-intelligent')
        except:
            self.honorary_message = honorary_message
