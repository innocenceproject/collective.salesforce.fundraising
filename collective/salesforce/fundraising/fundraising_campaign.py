import locale
import random
import smtplib
from datetime import date

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from Acquisition import aq_base
from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility
from zope.component import getMultiAdapter
from zope.component import queryUtility

from plone.i18n.locales.countries import CountryAvailability

from zope.interface import Interface
from zope.interface import alsoProvides
from zope import schema
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent
from zope.lifecycleevent.interfaces import IObjectModifiedEvent

from plone.z3cform.interfaces import IWrappedForm

from plone.app.textfield import RichText
from plone.app.textfield.value import RichTextValue
from plone.app.layout.viewlets.interfaces import IHtmlHead
from plone.app.layout.viewlets.interfaces import IPortalTop
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.namedfile.field import NamedBlobImage
from plone.memoize import instance
from plone.uuid.interfaces import IUUID

from plone.portlets.interfaces import IPortletAssignmentMapping
from plone.portlets.interfaces import IPortletManager
from plone.portlets.constants import CONTENT_TYPE_CATEGORY

from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.ATContentTypes.interfaces import IATDocument

from dexterity.membrane.membrane_helpers import get_membrane_user

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import sanitize_soql
from collective.salesforce.fundraising.utils import compare_sf_ids
from collective.salesforce.fundraising.us_states import states_list
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE

from collective.oembed.interfaces import IConsumer

from collective.stripe.controlpanel import MODE_VOCABULARY
from collective.stripe.interfaces import IStripeEnabledView
from collective.stripe.interfaces import IStripeModeChooser

from collective.chimpdrill.utils import IMailsnakeConnection


@grok.provider(schema.interfaces.IContextSourceBinder)
def availableThankYouTemplates(context):
    query = { "portal_type" : "collective.chimpdrill.template" }
    terms = []
    pc = getToolByName(context, 'portal_catalog')
    res = pc.searchResults(**query)
    for template in res:
        obj = template.getObject()
        uuid = IUUID(obj)
        if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IThankYouEmail':
            terms.append(SimpleVocabulary.createTerm(uuid, obj.title))
    return SimpleVocabulary(terms)

@grok.provider(schema.interfaces.IContextSourceBinder)
def availableHonoraryTemplates(context):
    query = { "portal_type" : "collective.chimpdrill.template" }
    terms = []
    pc = getToolByName(context, 'portal_catalog')
    res = pc.searchResults(**query)
    for template in res:
        obj = template.getObject()
        uuid = IUUID(obj)
        if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IHonoraryEmail':
            terms.append(SimpleVocabulary.createTerm(uuid, obj.title))
    return SimpleVocabulary(terms)

@grok.provider(schema.interfaces.IContextSourceBinder)
def availableMemorialTemplates(context):
    query = { "portal_type" : "collective.chimpdrill.template" }
    terms = []
    pc = getToolByName(context, 'portal_catalog')
    res = pc.searchResults(**query)
    for template in res:
        obj = template.getObject()
        uuid = IUUID(obj)
        if obj.template_schema == 'collective.salesforce.fundraising.chimpdrill.IMemorialEmail':
            terms.append(SimpleVocabulary.createTerm(uuid, obj.title))
    return SimpleVocabulary(terms)

class IFundraisingCampaign(form.Schema, IImageScaleTraversable):
    """
    A Fundraising Campaign linked to a Campaign in Salesforce.com
    """
    body = RichText(
        title=u"Fundraising Pitch",
        description=u"The body of the pitch for this campaign shown above the donation form",
    )

    image = NamedBlobImage(
        title=u"Image",
        description=u"The main promotional image for this campaign.  This image will be shown big and small so pick an image that looks good at all sizes.",
    )

    header_image = NamedBlobImage(
        title=u"Header Image",
        description=u"If provided, this image will be used as the header graphic for the campaign instead of the site default.",
        required=False,
    )

    hide_title_and_description = schema.Bool(
        title=u"Hide Title and Description?",
        description=u"If checked, the campaign's title and description will be rendered on the page but hidden from view.  This is useful if you are using a custom header image that already contains the title and description content.",
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

    stripe_mode = schema.Choice(
        title=u"Stripe Payment Processing Mode",
        description=u"Stripe can either run in test or live mode.  Test mode allows you to successfully process donations using a dummy card number.  Real cards will fail in test mode.  Live mode is the full production mode which only accepts valid cards",
        vocabulary=MODE_VOCABULARY,
        default=u"test",
    )

    stripe_recurring_plan = schema.Choice(
        title=u"Stripe Recurring Plan",
        description=u"If selected, recurring donations will be enabled on the Stripe form for this campaign and will subscribe donors who opt for recurring to the selected plan in Stripe",
        vocabulary=u'collective.stripe.plans',
        required=False,
    )

    donation_form_header = schema.TextLine(
        title=u"Header for Donation Forms",
        description=u"This header will be displayed above donation forms for this campaign.  If no value is supplied, the default site-wide header will be used.",
        required=False,
    )

    donation_form_description = RichText(
        title=u"Description for Donation Forms",
        description=u"If provided, this value will be displayed above donation forms for this campaign.  If no value is provided, and a site-wide default is set, that default will be used.",
        required=False,
    )

    chimpdrill_template_thank_you = schema.Choice(
        title=u"Thank You Email Template",
        description=u"The Mailchimp/Mandrill template to use when sending thank you emails for this campaign",
        required=False,
        source=availableThankYouTemplates,
    )

    chimpdrill_template_honorary = schema.Choice(
        title=u"Honorary Email Template",
        description=u"The Mailchimp/Mandrill template to use when sending honorary emails for this campaign",
        required=False,
        source=availableHonoraryTemplates,
    )

    chimpdrill_template_memorial = schema.Choice(
        title=u"Memorial Email Template",
        description=u"The Mailchimp/Mandrill template to use when sending memorial emails for this campaign",
        required=False,
        source=availableMemorialTemplates,
    )

    chimpdrill_list_donors = schema.Choice(
        title=u"Mailchimp List - Donors",
        description=u"If selected, donors to this campaign will automatically be added to the selected list",
        required=False,
        vocabulary=u"collective.chimpdrill.lists",
    )
        
    chimpdrill_list_fundraisers = schema.Choice(
        title=u"Mailchimp List - Personal Fundraisers",
        description=u"If selected, personal fundraisers in this campaign will automatically be added to the selected list.",
        required=False,
        vocabulary=u"collective.chimpdrill.lists",
    )

    donation_receipt_legal = schema.Text(
        title=_(u"Donation Receipt Legal Text"),
        description=_(u"Enter any legal text you want displayed at the bottom of html receipt.  For example, you might want to state that all donations are tax deductable and include the organization's Tax ID.  This field overrides the site-wide default receipt legal text configured in Fundraising Settings.  If no value is provided, the site default text will be used."),
        required=False,
    )

    fundraising_seals = schema.List(
        title=u"Fundraising Seals Override",
        description=u"Normally, the site default seals are shown on a campaign.  If you want to override the seals displayed only on this campaign, enter the full physical path to the seals here",
        value_type=schema.TextLine(),
        required=False,
    )

    form.model("models/fundraising_campaign.xml")

alsoProvides(IFundraisingCampaign, IContentType)

class IFundraisingCampaignPage(Interface):
    """ Marker interface for campaigns that act like a fundraising campaign """

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
    return get_settings().available_form_views

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
    grok.implements(IStripeModeChooser)

    def is_personal(self):
        return False

    def get_stripe_mode(self):
        return getattr(self.get_fundraising_campaign(), 'stripe_mode', 'test')

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

            self.reindexObject(idxs=['get_goal_percent', 'donations_total', 'donations_count'])

            # Check if this is a personal campaign
            if hasattr(self, 'parent_sf_id'):
                # Clear the cached list of donations for the personal campaign so a fresh list is fetched next time
                self.clear_donations_from_cache()

                # If this is a child campaign and its parent campaign is the parent
                # in Plone, add the value to the parent's donations_total
                parent = self.get_fundraising_campaign()

                if parent.sf_object_id == self.parent_sf_id:
                    parent_total = 0
                    if parent.donations_total:
                        parent_total = int(parent.donations_total)
                    parent_count = 0
                    if parent.donations_count:
                        parent_count = int(parent.donations_count)
                    parent.donations_total = parent.donations_total + amount
                    parent.donations_count = parent.donations_count + 1

                parent.reindexObject(idxs=['get_goal_percent', 'donations_total', 'donations_count'])

    def get_external_media_oembed(self):
        external_media = getattr(self, 'external_media_url', None)
        if external_media:
            consumer = getUtility(IConsumer)
            # FIXME - don't hard code maxwidth
            return consumer.get_data(self.external_media_url, maxwidth=270).get('html')
           
    def clear_donation_from_cache(self, donation_id, amount):
        """ Clears a donation from the cache.  This is useful if its value needs to be refreshed
            on the next time it's called but you don't want to call it now. """
        if not hasattr(self, '_memojito_'):
            return None
        donation_key = ('lookup_donation', (self, donation_id, amount), frozenset([]))
        lineitem_key = ('lookup_donation_product_line_items',
                        (self, donation_id),
                        frozenset([]))
        self._memojito_.clear()
        if self._memojito_.has_key(donation_key):
            del self._memojito_[donation_key]
        if self._memojito_.has_key(lineitem_key):
            del self._memojito_[lineitem_key]
 
    @instance.memoize
    def lookup_donation(self, donation_id, amount):
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
        return sfbc.query(RECEIPT_SOQL % (donation_id, amount, self.sf_object_id))

    @instance.memoize
    def lookup_donation_product_line_items(self, donation_id):
        """get any line-items for the given opportunity

        resolve them to object title, price and quantity before caching result
        """
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
        pc = getToolByName(self, 'portal_catalog')
        typename = 'collective.salesforce.fundraising.donationproduct'
        items = sfbc.query(LINE_ITEM_SOQL % donation_id)
        lines = []
        for item in items:
            qty = int(item['Quantity'])
            prod_id = item['PricebookEntry']['Product2Id']
            entry_id = item['PricebookEntry']['Id']
            brains = pc(portal_type=typename, sf_object_id=prod_id)
            if not brains:
                continue
            prod = brains[0].getObject()
            lines.append({'product': prod.title,
                          'price': prod.price,
                          'date': prod.date,
                          'location': prod.location,
                          'notes': prod.notes,
                          'quantity': qty})
        return lines

    def get_header_image_url(self):
        local_image = getattr(self, 'header_image', None)
        if local_image and local_image.filename:
            return '%s/@@images/header_image' % self.absolute_url()

        settings = get_settings()
        return getattr(settings, 'default_header_image_url', None)


    def get_display_goal_pct(self):
        settings = get_settings()
        return settings.campaign_status_completion_threshold

    def send_donation_receipt(self, request, donation_id, amount):
        donation = self.lookup_donation(donation_id, amount)
        settings = get_settings()
        
        # if this donation was a product purchase, get line items:
        lineitems = []
        is_product_purchase = False
        # the id we store in settings may or may not exist, and may or may not
        # be identical to the one we get back (sf passes ids of two different
        # lengths, although they mark the same record)
        recordtype = donation[0]['Opportunity']['RecordTypeId']
        producttype = settings.sf_opportunity_record_type_product
        if recordtype and producttype:
            if compare_sf_ids(recordtype, producttype):
                is_product_purchase = True
            
        if is_product_purchase:
            lineitems = self.lookup_donation_product_line_items(donation_id)

        # Construct the email bodies
        pt = getToolByName(self, 'portal_transforms')
        email_view = getMultiAdapter((self, request), name='thank-you-email')
        email_view.set_donation_keys(donation_id, amount)
        email_body = email_view()
        txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

        # Determine to and from addresses
        portal_url = getToolByName(self, 'portal_url')
        portal = portal_url.getPortalObject()
        mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))
        mail_to = email_view.receipt_view.contact.Email

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

        except smtplib.SMTPRecipientsRefused:
            # fail silently so errors here don't freak out the donor about their transaction which was successful by this point
            pass

    def get_fundraising_campaign_page(self):
        """ Returns the fundraising campaign page instance, either a Fundraising Campaign or a Personal Campaign Page """
        return self


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

    def get_mailchimp_connection(self):
        return getUtility(IMailsnakeConnection).get_mailchimp()

    def setup_mailchimp_list_donors(self, mc=None):
        list_id = self.chimpdrill_list_donors
        if not list_id:
            return

        if not mc:
            mc = self.get_mailchimp_connection()

        merge_vars = [
            {
                'tag': 'L_AMOUNT', 
                'name': 'Last Donation Amount', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'L_DATE', 
                'name': 'Last Donation Date', 
                'options': {'field_type': 'date'},
            },
            {
                'tag': 'L_RECEIPT', 
                'name': 'Last Donation Receipt URL', 
                'options': {'field_type': 'url'},
            },
            {
                'tag': 'REC_START', 
                'name': 'Recurring Start Date', 
                'options': {'field_type': 'date'},
            },
            {
                'tag': 'REC_LAST', 
                'name': 'Recurring Last Donation Date', 
                'options': {'field_type': 'date'},
            },
            {
                'tag': 'REC_AMOUNT', 
                'name': 'Recurring Amount', 
                'options': {'field_type': 'number'},
            },
        ]
       
        existing = {} 
        for var in mc.listMergeVars(id=list_id):
            existing[var['tag']] = var

        # Create any merge vars in the list that need to be created
        for var in merge_vars:
            if not existing.has_key(var['tag']):
                mc.listMergeVarAdd(id=list_id, tag=var['tag'], name=var['name'], options=var['options'])


    def setup_mailchimp_list_fundraisers(self, mc=None):
        list_id = self.chimpdrill_list_fundraisers
        if not list_id:
            return

        if not mc:
            mc = self.get_mailchimp_connection()
       
        merge_vars = [
            {
                'tag': 'PF_GOAL', 
                'name': 'Personal Fundraising Goal', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'PF_COUNT', 
                'name': 'Personal Fundraising - Number of Donations', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'PF_RAISED', 
                'name': 'Personal Fundraising - Total Raised', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'PF_PERCENT', 
                'name': 'Personal Fundraising - Percent of Goal Raised', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'PF_REMAIN', 
                'name': 'Personal Fundraising - Percent of Goal Remaining', 
                'options': {'field_type': 'number'},
            },
            {
                'tag': 'PF_URL', 
                'name': 'Personal Fundraising - Page URL', 
                'options': {'field_type': 'url'},
            },
        ]

        existing = {} 
        for var in mc.listMergeVars(id=list_id):
            existing[var['tag']] = var

        # Create any merge vars in the list that need to be created
        for var in merge_vars:
            if not existing.has_key(var['tag']):
                mc.listMergeVarAdd(id=list_id, tag=var['tag'], name=var['name'], options=var['options'])

        
@grok.subscribe(IFundraisingCampaign, IObjectModifiedEvent)
def setupMailchimpLists(campaign, event):
    campaign.setup_mailchimp_list_donors()
    campaign.setup_mailchimp_list_fundraisers()


class CampaignView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.implements(IStripeEnabledView)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

    def addcommas(self, number):
        locale.setlocale(locale.LC_ALL, 'en_US')
        return locale.format('%d', number, grouping=True)

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
        donation_form_tabs = self.context.donation_form_tabs
        if donation_form_tabs:
            for tab in donation_form_tabs:
                parts = tab.split('|')
                if len(parts) == 1:
                    label = parts[0]
                else:
                    label = parts[1]
                view_name = parts[0]
           
                html = self.context.unrestrictedTraverse(view_name.split('/'))
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

        settings = get_settings()
        self.ssl_seal = settings.ssl_seal

        for name in ['donation_form_header', 'donation_form_description']:
            setattr(self, name, self.get_local_or_default(name))
    
    def get_local_or_default(self, field):
        """for fields of the context object with both local and site-wide 
        default values. Return the local value if provided, else return the 
        setting, else return None

        always looks for values on the fundraising campaign object only
        """
        local_campaign = aq_base(self.context.get_fundraising_campaign())
        val = getattr(local_campaign, field, None)
        if not val:
            settings = get_settings()
            val = getattr(settings, field, None)
        # convert rich text objects, if present:
        if val and isinstance(val, RichTextValue):
            val = val.output

        return val


class ThankYouView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('thank-you')
    grok.template('thank-you')

    def update(self):
        # Fetch some values that should have been passed from the redirector
        self.donation_id = self.request.form.get('donation_id', None)
        self.amount = self.request.form.get('amount', None)
        if not self.donation_id:
            self.donation_id = self.request.form.get('form.widgets.donation_id', None)
        if not self.amount:
            self.amount = self.request.form.get('form.widgets.amount', None)

        self.receipt_view = None
        self.receipt = None
        if self.donation_id and self.amount:
            self.amount = int(self.amount)
            self.receipt_view = getMultiAdapter((self.context, self.request), name='donation-receipt')
            self.receipt_view.set_donation_keys(self.donation_id, self.amount)
            self.receipt = self.receipt_view()

        # Create a wrapped form for inline rendering
        from collective.salesforce.fundraising.forms import CreateDonorQuote
        # Only show the form if a valid receipt is being displayed
        if self.context.can_create_donor_quote() and self.receipt_view:
            self.donor_quote_form = CreateDonorQuote(self.context, self.request)
            alsoProvides(self.donor_quote_form, IWrappedForm)
            self.donor_quote_form.update()
            self.donor_quote_form.widgets.get('name').value = u'%s %s' % (self.receipt_view.contact.FirstName, self.receipt_view.contact.LastName)
            self.donor_quote_form.widgets.get('contact_sf_id').value = unicode(self.receipt_view.contact.Id)
            self.donor_quote_form.widgets.get('donation_id').value = unicode(self.donation_id)
            self.donor_quote_form.widgets.get('amount').value = unicode(self.amount)
            self.donor_quote_form_html = self.donor_quote_form.render()

        # Determine any sections that should be collapsed
        self.hide = self.request.form.get('hide', [])
        if self.hide:
            self.hide = self.hide.split(',')

    def render_janrain_share(self):
        settings = get_settings()
        comment = settings.thank_you_share_message
        if not comment:
            comment = ''

        amount_str = ''
        if self.amount:
            amount_str = _(u' $%s' % self.amount)
            comment = comment.replace('{{ amount }}', str(self.amount))
        else:
            comment = comment.replace('{{ amount }}', '')
        
        return SHARE_JS_TEMPLATE % {
            'link_id': 'share-message-thank-you',
            'url': self.context.absolute_url() + '?SOURCE_CODE=thank_you_share',
            'title': self.context.title.replace("'","\\'"),
            'description': self.context.description.replace("'","\\'"),
            'image': self.context.absolute_url() + '/@@images/image',
            'message': comment,
        }

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
                honorary = {
                    'type': self.request.form.get('honorary_type', None),
                    'notification_type': self.request.form.get('honorary_notification_type', None),
                    'first_name': self.request.form.get('honorary_first_name', None),
                    'last_name': self.request.form.get('honorary_last_name', None),
                    'recipient_first_name': self.request.form.get('honorary_recipient_first_name', None),
                    'recipient_last_name': self.request.form.get('honorary_recipient_last_name', None),
                    'email': self.request.form.get('honorary_email', None),
                    'address': self.request.form.get('honorary_address', None),
                    'city': self.request.form.get('honorary_city', None),
                    'state': self.request.form.get('honorary_state', None),
                    'zip': self.request.form.get('honorary_zip', None),
                    'country': self.request.form.get('honorary_country', None),
                    'message': self.request.form.get('honorary_message', None),
                }

                # Dump the data into Salesforce
                sfbc = getToolByName(self.context, 'portal_salesforcebaseconnector')
                sfbc.update({
                    'type': 'Opportunity',
                    'Id': self.donation_id,
                    'Honorary_Type__c': honorary['type'],
                    'Honorary_Notification_Type__c': honorary['notification_type'],
                    'Honorary_First_Name__c': honorary['first_name'],
                    'Honorary_Last_Name__c': honorary['last_name'],
                    'Honorary_Recipient_First_Name__c': honorary['recipient_first_name'],
                    'Honorary_Recipient_Last_Name__c': honorary['recipient_last_name'],
                    'Honorary_Email__c': honorary['email'],
                    'Honorary_Street_Address__c': honorary['address'],
                    'Honorary_City__c': honorary['city'],
                    'Honorary_State__c': honorary['state'],
                    'Honorary_Zip__c': honorary['zip'],
                    'Honorary_Country__c': honorary['country'],
                    'Honorary_Message__c': honorary['message'],
                })

                # Expire the donation in the cache so the new Honorary values are looked up next time
                self.context.clear_donation_from_cache(self.donation_id, self.amount)

                # If there was an email passed and we're supposed to send an email, send the email
                if honorary['notification_type'] == 'Email' and honorary['email']:

                    settings = get_settings() 

                    # Construct the email bodies
                    pt = getToolByName(self.context, 'portal_transforms')
                    if honorary['type'] == u'Honorary':
                        email_view = getMultiAdapter((self.context, self.request), name='honorary-email')
                    else:
                        email_view = getMultiAdapter((self.context, self.request), name='memorial-email')

                    email_view.set_honorary_info(
                        donor = '%(FirstName)s %(LastName)s' % self.receipt_view.contact,
                        honorary = honorary,
                    )
                    email_body = email_view()
        
                    txt_body = pt.convertTo('text/-x-web-intelligent', email_body, mimetype='text/html')

                    # Construct the email message                
                    portal_url = getToolByName(self.context, 'portal_url')
                    portal = portal_url.getPortalObject()

                    mail_from = '"%s" <%s>' % (portal.getProperty('email_from_name'), portal.getProperty('email_from_address'))
                    mail_cc = self.receipt_view.contact.Email

                    msg = MIMEMultipart('alternative')
                    if honorary['type'] == 'Memorial': 
                        msg['Subject'] = 'Gift received in memory of %(first_name)s %(last_name)s' % honorary
                    else:
                        msg['Subject'] = 'Gift received in honor of %(first_name)s %(last_name)s' % honorary
                    msg['From'] = mail_from
                    msg['To'] = honorary['email']
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
                self.request.response.redirect('%s/thank-you?donation_id=%s&amount=%i' % (self.context.absolute_url(), self.donation_id, self.amount))

        self.countries = CountryAvailability().getCountryListing()
        self.countries.sort()

        self.states = states_list

        return self.form_template()

class ShareView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
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
                parent_res = self.context.get_fundraising_campaign().listFolderContents(contentFilter = {
                    'portal_type': 'collective.salesforce.fundraising.sharemessage'
                })
                if len(parent_res) + len(res) > 3:
                    res = res + random.sample(parent_res, 3 - len(res))
                elif len(parent_res) + len(res) <= 3:
                    res = res + parent_res
        # If there are more than 3 messages are found, select 3 at random from the list
        if len(res) > 3:
            res = random.sample(res, 3)

        self.messages = []
        for message in res:
            self.message_view = getMultiAdapter((message, self.request), name='view')
            self.message_view.set_url(self.context.absolute_url() + '?source_campaign=')
            self.messages.append(self.message_view())

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
    Opportunity.npe03__Recurring_Donation__c, 
    Opportunity.Honorary_Type__c, 
    Opportunity.Honorary_First_Name__c, 
    Opportunity.Honorary_Last_Name__c, 
    Opportunity.Honorary_Recipient_First_Name__c, 
    Opportunity.Honorary_Recipient_Last_Name__c, 
    Opportunity.Honorary_Notification_Type__c, 
    Opportunity.Honorary_Email__c, 
    Opportunity.Honorary_Street_Address__c, 
    Opportunity.Honorary_City__c, 
    Opportunity.Honorary_State__c, 
    Opportunity.Honorary_Zip__c, 
    Opportunity.Honorary_Country__c, 
    Opportunity.Honorary_Message__c, 
    Opportunity.RecordTypeId, 
    Contact.Id, 
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

LINE_ITEM_SOQL = """SELECT
    Quantity, 
    PricebookEntry.Product2Id, 
    PricebookEntry.Id 
    FROM OpportunityLineItem 
    WHERE 
        OpportunityId = '%s'
"""

class DonationReceipt(grok.View):
    """ Looks up an opportunity in Salesforce and prepares a donation receipt.

    Uses amount and id as keys
    """
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('donation-receipt')
    grok.template('donation-receipt')

    def update(self):
        if not getattr(self, 'donation_id', None):
            self.donation_id = sanitize_soql(self.request.form.get('donation_id'))

        if not getattr(self, 'amount', None):
            self.amount = int(self.request.form.get('amount'))
        
        refresh = self.request.form.get('refresh') == 'true'
        res = self.context.lookup_donation(self.donation_id, self.amount)
        
        if not len(res['records']):
            raise ValueError('Donation with id %s and amount %s was not found.' % (donation_id, amount))

        self.line_items = self.context.lookup_donation_product_line_items(
            self.donation_id)

        settings = get_settings()
        self.organization_name = settings.organization_name
        self.donation_receipt_legal = settings.donation_receipt_legal

        self.donation = res['records'][0].Opportunity
        self.contact = res['records'][0].Contact

    def set_donation_keys(self, donation_id, amount):
        self.donation_id = donation_id
        self.amount = int(amount)


class ThankYouEmail(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('thank-you-email')
    grok.template('thank-you-email')
    
    def update(self):
        if not getattr(self, 'donation_id', None):
            self.donation_id = sanitize_soql(self.request.form.get('donation_id'))

        if not getattr(self, 'amount', None):
            self.amount = int(self.request.form.get('amount'))
        
        self.receipt_view = getMultiAdapter((self.context, self.request), name='donation-receipt')
        self.receipt_view.set_donation_keys(self.donation_id, self.amount)
        self.receipt = self.receipt_view()

        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer

    def set_donation_keys(self, donation_id, amount):
        self.donation_id = donation_id
        self.amount = int(amount)


class HonoraryEmail(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    
    grok.name('honorary-email')
    grok.template('honorary-email')
    
    def update(self):
        if self.request.get('show_template', None) == 'true':
            # Enable rendering of the template without honorary info
            self.set_honorary_info(
                donor = '[Your Name]',
                honorary = {
                    'last_name': '[Memory Name]',
                    'recipient_first_name': '[Recipient First Name]',
                    'recipient_last_name': '[Recipient Last Name]',
                    'message': '[Message]',
                }
            )
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.request['amount']
        
    def set_honorary_info(self, donor, honorary):
        self.donor = donor
        self.honorary = honorary

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')
        if self.honorary['message']:
            try:
                self.honorary['message'] = pt.convertTo('text/html', self.honorary['message'], mimetype='text/-x-web-intelligent')
            except:
                self.honorary['message'] = honorary['message']


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
                donor = '[Your Name]',
                honorary = {
                    'first_name': '',
                    'last_name': '[Memory Name]',
                    'recipient_first_name': '[Recipient First Name]',
                    'recipient_last_name': '[Recipient Last Name]',
                    'message': '[Message]',
                }
            )
            
        settings = get_settings()
        self.email_header = settings.email_header
        self.email_footer = settings.email_footer
        self.organization_name = settings.organization_name
        self.amount = None
        if self.request.form.get('show_amount', None) == 'Yes':
            self.amount = self.request.form['amount']
        
    def set_honorary_info(self, donor, honorary):
        self.donor = donor
        self.honorary = honorary

        # Attempt to perform a basic text to html conversion on the message text provided
        pt = getToolByName(self.context, 'portal_transforms')

        if self.honorary['message']:
            try:
                self.honorary['message'] = pt.convertTo('text/html', self.honorary['message'], mimetype='text/-x-web-intelligent')
            except:
                self.honorary['message'] = honorary['message']


class PostDonationErrorView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.name('post_donation_error')
    grok.require('zope2.View')
    grok.template('post_donation_error')

class ClearCache(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('cmf.ModifyPortalContent')
    grok.name('clear-cache')
    
    def render(self):
        self.request.response.redirect(self.context.absolute_url())

# Pages added inside the campaign need to display the same portlets as the
# campaign.
@grok.subscribe(IATDocument, IObjectAddedEvent)
def activate_campaign_portlets(page, event):
    if IFundraisingCampaign.providedBy(event.newParent):
        category = CONTENT_TYPE_CATEGORY
        pt = 'collective.salesforce.fundraising.fundraisingcampaign'
        campaign = event.newParent
        campaign_manager = getUtility(IPortletManager, name='plone.rightcolumn',
                context=campaign)
        campaign_manager_assignments = campaign_manager[category]
        page_manager = queryUtility(IPortletManager, name='plone.rightcolumn',
                context=page)
        if page_manager is not None:
            page_manager_assignments = getMultiAdapter((page,
                page_manager), IPortletAssignmentMapping)
            content_type_assignments = campaign_manager_assignments.get(pt, None)
            if content_type_assignments is None:
                return
            for name, assignment in content_type_assignments.items():
                page_manager_assignments[name] = assignment

FACEBOOK_META_TEMPLATE = """
  <meta property="og:title" content="%(title)s">
  <meta property="og:description" content="%(description)s">
  <meta property="og:url" content="%(url)s">
  <meta property="og:image" content="%(url)s/@@images/image">
"""

class FacebookMetaViewlet(grok.Viewlet):
    """ Add Facebook og tags to head using campaign info """

    grok.name('collective.salesforce.fundraising.FacebookMetaViewlet')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaignPage)
    grok.viewletmanager(IHtmlHead)

    def render(self):
        return FACEBOOK_META_TEMPLATE % {
            'title': self.context.title,
            'description': self.context.description,
            'url': self.context.absolute_url(),
        }

class HeaderImageViewlet(grok.Viewlet):
    grok.name('collective.salesforce.fundraising.HeaderImageViewlet')
    grok.require('zope2.View')
    grok.context(Interface)
    grok.viewletmanager(IPortalTop)

    def render(self):
        campaign = getattr(self.context, 'get_fundraising_campaign', None)
        if not campaign:
            return ''
        campaign = campaign()
        image_url = campaign.get_header_image_url()
        if not image_url:
            return ''
        return '<div id="fundraising-campaign-header-image"><a href="%s"><img src="%s/campaign_header" alt="%s" /></a></div>' % (
            self.context.absolute_url(), image_url, self.context.title)

class PersonalLoginViewlet(grok.Viewlet):
    grok.name('collective.salesforce.fundraising.PersonalLoginViewlet')
    grok.require('zope2.View')
    grok.context(IFundraisingCampaignPage)
    grok.template('personal-login')
    grok.viewletmanager(IPortalTop)

    def update(self):
        pm = getToolByName(self.context, 'portal_membership')
        self.person = None
        self.is_anon = pm.isAnonymousUser()
        self.is_personal_page = False

        from collective.salesforce.fundraising.personal_campaign_page import IPersonalCampaignPage
        if IPersonalCampaignPage.providedBy(self.context):
            self.is_personal_page = True

        if not self.is_anon:
            self.enabled = True
        else:
            self.enabled = self.context.get_fundraising_campaign().allow_personal
    
        if self.is_personal_page:
            self.enabled = True

        if not self.enabled:
            return

        mt = getToolByName(self.context, 'membrane_tool')
        if not self.is_anon:
            res = mt.searchResults(getUserName = pm.getAuthenticatedMember().getId())
            if res:
                self.person = res[0].getObject()

