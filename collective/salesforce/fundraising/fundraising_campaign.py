import random
import smtplib
from rwproperty import getproperty, setproperty
from datetime import date

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from Acquisition import aq_base
from five import grok
from plone.directives import dexterity, form
from plone.supermodel import model

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

from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.ATContentTypes.interfaces import IATDocument

from dexterity.membrane.membrane_helpers import get_membrane_user

from collective.simplesalesforce.utils import ISalesforceUtility

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import sanitize_soql
from collective.salesforce.fundraising.utils import compare_sf_ids
from collective.salesforce.fundraising.utils import get_person_by_sf_id
from collective.salesforce.fundraising.us_states import states_list
from collective.salesforce.fundraising.janrain.rpx import SHARE_JS_TEMPLATE

from collective.oembed.interfaces import IConsumer

from collective.stripe.controlpanel import MODE_VOCABULARY
from collective.stripe.interfaces import IStripeEnabledView
from collective.stripe.interfaces import IStripeModeChooser

from collective.chimpdrill.utils import IMailsnakeConnection


@grok.provider(schema.interfaces.IContextSourceBinder)
def availableDonationForms(context):
    query = { 
        "portal_type" : "collective.salesforce.fundraising.productform",
        "path" : '/'.join(context.getPhysicalPath()),
    }
    terms = []
    settings = get_settings()
    default = settings.default_donation_form
    terms.append(SimpleVocabulary.createTerm(default, default, 'Stripe Donation Form'))

    pc = getToolByName(context, 'portal_catalog')
    res = pc.searchResults(**query)
    for form in res:
        form_id = form.id + '/donation_form_stripe'
        terms.append(SimpleVocabulary.createTerm(form_id, form_id, 'Product Form: ' + form.Title))
    return SimpleVocabulary(terms)

class IFundraisingCampaign(model.Schema, IImageScaleTraversable):
    """
    A Fundraising Campaign linked to a Campaign in Salesforce.com
    """
    model.load("models/fundraising_campaign.xml")

alsoProvides(IFundraisingCampaign, IContentType)

class IFundraisingCampaignPage(Interface):
    """ Marker interface for campaigns that act like a fundraising campaign """

#@form.default_value(field=IFundraisingCampaign['thank_you_message'])
#def thankYouDefaultValue(data):
#    return get_settings().default_thank_you_message
#
#@form.default_value(field=IFundraisingCampaign['default_personal_appeal'])
#def defaultPersonalAppealDefaultValue(data):
#    return get_settings().default_personal_appeal
#
#@form.default_value(field=IFundraisingCampaign['default_personal_thank_you'])
#def defaultPersonalThankYouDefaultValue(data):
#    return get_settings().default_personal_thank_you_message
#
#@form.default_value(field=IFundraisingCampaign['donation_form_tabs'])
#def defaultDonationFormTabsValue(data):
#    return get_settings().available_form_views

@grok.subscribe(IFundraisingCampaign, IObjectAddedEvent)
def handleFundraisingCampaignCreated(campaign, event):
    # Add campaign in Salesforce if it doesn't have a Salesforce id yet
    if getattr(campaign, 'sf_object_id', None) is None:
        sfconn = getUtility(ISalesforceUtility).get_connection()

        settings = get_settings()

        # Only parse the dates if they have a value
        start_date = campaign.date_start
        if start_date:
            start_date = start_date.isoformat()
        end_date = campaign.date_end
        if end_date:
            end_date = end_date.isoformat()

        data = {
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

        res = sfconn.Campaign.create(data)
        if not res['success']:
            raise Exception(res['errors'][0])
        campaign.sf_object_id = res['id']
        campaign.reindexObject(idxs=['sf_object_id'])


class FundraisingCampaignPage(object):
    grok.implements(IStripeModeChooser)

    # Implementations of default value inheritance for some fields
    def get_local_or_default(self, field):
        """Get a field's value using inheritance of [page ->] campaign -> global """

        # Try page
        page = aq_base(self.get_fundraising_campaign_page())
        val = getattr(page, '_%s' % field, None)
        if val is None:
            # For backwards compatibility, check __dict__ for a previous value and port it
            if page.__dict__.has_key(field):
                val = page.__dict__[field]
                setattr(self, '_%s' % field, val)

        test_val = val
        # check if the output of a rich text field is empty
        if isinstance(val, RichTextValue):
            test_val = val.output
        if test_val is not None:
            return val

        # Use default if no local value
        return self.get_default(field)

    def get_default(self, field):
        # Skip lookup if there is no id (i.e. object is still being created)
        if self.id:
            # Try campaign if different from page (i.e. personal campaign page or campaign variation)
            campaign = self.get_fundraising_campaign()
            if campaign != self.get_fundraising_campaign_page():
                val = getattr(campaign, '_%s' % field, None)
                # convert rich text objects, if present:
                if isinstance(val, RichTextValue):
                    val = val.output
                if val is not None:
                    return val

        # Try global using 'default_' as field name prefix for settings
        settings = get_settings()
        val = getattr(settings, 'default_%s' % field, None)

        return val

    @getproperty
    def external_media_url(self):
        return self.get_local_or_default('external_media_url')
    @setproperty
    def external_media_url(self, external_media_url):
        if external_media_url != self.get_default('external_media_url'):
            self._external_media_url = external_media_url
    
    @getproperty
    def body(self):
        return self.get_local_or_default('body')
    @setproperty
    def body(self, body):
        if body != self.get_default('body'):
            self._body = body
    
    @getproperty
    def thank_you_message(self):
        return self.get_local_or_default('thank_you_message')
    @setproperty
    def thank_you_message(self, thank_you_message):
        if thank_you_message != self.get_default('thank_you_message'):
            self._thank_you_message = thank_you_message
    
    @getproperty
    def donation_receipt_legal(self):
        return self.get_local_or_default('donation_receipt_legal')
    @setproperty
    def donation_receipt_legal(self, donation_receipt_legal):
        if donation_receipt_legal != self.get_default('donation_receipt_legal'):
            self._donation_receipt_legal = donation_receipt_legal
    
    @getproperty
    def goal(self):
        return self.get_local_or_default('goal')
    @setproperty
    def goal(self, goal):
        if goal != self.get_default('goal'):
            self._goal = goal
    
    @getproperty
    def start_date(self):
        return self.get_local_or_default('start_date')
    @setproperty
    def start_date(self, start_date):
        if start_date != self.get_default('start_date'):
            self._start_date = start_date
    
    @getproperty
    def end_date(self):
        return self.get_local_or_default('end_date')
    @setproperty
    def end_date(self, end_date):
        if end_date != self.get_default('end_date'):
            self._end_date = end_date
    
    @getproperty
    def donation_form(self):
        return self.get_local_or_default('donation_form')
    @setproperty
    def donation_form(self, donation_form):
        if donation_form != self.get_default('donation_form'):
            self._donation_form = donation_form
    
    @getproperty
    def stripe_recurring_plan(self):
        return self.get_local_or_default('stripe_recurring_plan')
    @setproperty
    def stripe_recurring_plan(self, stripe_recurring_plan):
        if stripe_recurring_plan != self.get_default('stripe_recurring_plan'):
            self._stripe_recurring_plan = stripe_recurring_plan
    
    @getproperty
    def fundraising_seals(self):
        return self.get_local_or_default('fundraising_seals')
    @setproperty
    def fundraising_seals(self, fundraising_seals):
        if fundraising_seals != self.get_default('fundraising_seals'):
            self._fundraising_seals = fundraising_seals
    
    @getproperty
    def email_template_thank_you(self):
        return self.get_local_or_default('email_template_thank_you')
    @setproperty
    def email_template_thank_you(self, email_template_thank_you):
        if email_template_thank_you != self.get_default('email_template_thank_you'):
            self._email_template_thank_you = email_template_thank_you
    
    @getproperty
    def email_honorary(self):
        return self.get_local_or_default('email_honorary')
    @setproperty
    def email_honorary(self, email_honorary):
        if email_honorary != self.get_default('email_honorary'):
            self._email_honorary = email_honorary
    
    @getproperty
    def email_memorial(self):
        return self.get_local_or_default('email_memorial')
    @setproperty
    def email_memorial(self, email_memorial):
        if email_memorial != self.get_default('email_memorial'):
            self._email_memorial = email_memorial
    
    @getproperty
    def email_personal_page_created(self):
        return self.get_local_or_default('email_personal_page_created')
    @setproperty
    def email_personal_page_created(self, email_personal_page_created):
        if email_personal_page_created != self.get_default('email_personal_page_created'):
            self._email_personal_page_created = email_personal_page_created
    
    @getproperty
    def email_personal_page_donation(self):
        return self.get_local_or_default('email_personal_page_donation')
    @setproperty
    def email_personal_page_donation(self, email_personal_page_donation):
        if email_personal_page_donation != self.get_default('email_personal_page_donation'):
            self._email_personal_page_donation = email_personal_page_donation
    
    @getproperty
    def email_list_donors(self):
        return self.get_local_or_default('email_list_donors')
    @setproperty
    def email_list_donors(self, email_list_donors):
        if email_list_donors != self.get_default('email_list_donors'):
            self._email_list_donors = email_list_donors
    
    @getproperty
    def email_list_fundraisers(self):
        return self.get_local_or_default('email_list_fundraisers')
    @setproperty
    def email_list_fundraisers(self, email_list_fundraisers):
        if email_list_fundraisers != self.get_default('email_list_fundraisers'):
            self._email_list_fundraisers = email_list_fundraisers
   
    # FIXME: Control panel default for this field only has a url, need to interact properly with NamedBlobImage field 
    @getproperty
    def header_image(self):
        return self.get_local_or_default('header_image')
    @setproperty
    def header_image(self, header_image):
        if header_image != self.get_default('header_image'):
            self._header_image = header_image
    
    @getproperty
    def hide_title_and_description(self):
        return self.get_local_or_default('hide_title_and_description')
    @setproperty
    def hide_title_and_description(self, hide_title_and_description):
        if hide_title_and_description != self.get_default('hide_title_and_description'):
            self._hide_title_and_description = hide_title_and_description
    
    @getproperty
    def donation_form_header(self):
        return self.get_local_or_default('donation_form_header')
    @setproperty
    def donation_form_header(self, donation_form_header):
        if donation_form_header != self.get_default('donation_form_header'):
            self._donation_form_header = donation_form_header
    
    @getproperty
    def donation_form_description(self):
        return self.get_local_or_default('donation_form_description')
    @setproperty
    def donation_form_description(self, donation_form_description):
        if donation_form_description != self.get_default('donation_form_description'):
            self._donation_form_description = donation_form_description
    
    @getproperty
    def show_media_portlet(self):
        return self.get_local_or_default('show_media_portlet')
    @setproperty
    def show_media_portlet(self, show_media_portlet):
        if show_media_portlet != self.get_default('show_media_portlet'):
            self._show_media_portlet = show_media_portlet
    
    @getproperty
    def allow_personal(self):
        return self.get_local_or_default('allow_personal')
    @setproperty
    def allow_personal(self, allow_personal):
        if allow_personal != self.get_default('allow_personal'):
            self._allow_personal = allow_personal
    
    @getproperty
    def personal_only(self):
        return self.get_local_or_default('personal_only')
    @setproperty
    def personal_only(self, personal_only):
        if personal_only != self.get_default('personal_only'):
            self._personal_only = personal_only
    
    @getproperty
    def default_personal_appeal(self):
        return self.get_local_or_default('default_personal_appeal')
    @setproperty
    def default_personal_appeal(self, default_personal_appeal):
        if default_personal_appeal != self.get_default('default_personal_appeal'):
            self._default_personal_appeal = default_personal_appeal
    
    @getproperty
    def default_personal_thank_you(self):
        return self.get_local_or_default('default_personal_thank_you')
    @setproperty
    def default_personal_thank_you(self, default_personal_thank_you):
        if default_personal_thank_you != self.get_default('external_media_url'):
            self._default_personal_thank_you = default_personal_thank_you


    # Fundraising Campaign Page methods
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
           
    def get_header_image_url(self):
        local_image = getattr(self, 'header_image', None)
        if local_image and local_image.filename:
            return '%s/@@images/header_image' % self.absolute_url()

        settings = get_settings()
        return getattr(settings, 'default_header_image_url', None)


    def get_display_goal_pct(self):
        settings = get_settings()
        return settings.campaign_status_completion_threshold

    def get_fundraising_campaign_page(self):
        """ Returns the fundraising campaign page instance, either a Fundraising Campaign or a Personal Campaign Page """
        return self

    def get_email_campaign_data(self):
        campaign = self.get_fundraising_campaign()

        campaign_image_url = None
        if campaign.image and campaign.image.filename:
            campaign_image_url = '%s/@@images/image' % campaign.absolute_url()

        merge_vars = [
            {'name': 'campaign_name', 'content': campaign.title},
            {'name': 'campaign_url', 'content': campaign.absolute_url()},
            {'name': 'campaign_image_url', 'content': campaign_image_url},
            {'name': 'campaign_header_image_url', 'content': campaign.get_header_image_url()},
            {'name': 'campaign_goal', 'content': campaign.goal},
            {'name': 'campaign_raised', 'content': campaign.donations_total},
            {'name': 'campaign_percent', 'content': campaign.get_percent_goal()},
        ]

        if self.is_personal():
            page_merge_vars = [
                {'name': 'page_name', 'content': self.title},
                {'name': 'page_url', 'content': self.absolute_url()},
                {'name': 'page_image_url', 'content': '%s/@@images/image' % self.absolute_url()},
                {'name': 'page_goal', 'content': self.goal},
                {'name': 'page_raised', 'content': self.donations_total},
                {'name': 'page_percent', 'content': self.get_percent_goal()},
            ]

            person = self.get_fundraiser()
            if person is not None:
                page_merge_vars.append({'name': 'page_fundraiser_first', 'content': person.first_name})
                page_merge_vars.append({'name': 'page_fundraiser_last', 'content': person.last_name})

            merge_vars.extend(page_merge_vars)

        return {
            'merge_vars': merge_vars,
            'blocks': [],
        }

class FundraisingCampaign(dexterity.Container, FundraisingCampaignPage):
    grok.implements(IFundraisingCampaign, IFundraisingCampaignPage)

    def absolute_url(self, do_not_cache=False):
        """ Fallback to cached value if no REQUEST available """
        url = super(FundraisingCampaign, self).absolute_url()
        if do_not_cache:
            return url
        cached = getattr(aq_base(self), '_absolute_url', None)
        if url.startswith('http'):
            if cached is None or cached != url:
                self._absolute_url = url
            
        return getattr(aq_base(self), '_absolute_url', url)

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
        list_id = self.email_list_donors
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
        list_id = self.email_list_fundraisers
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
        return '{0:,}'.format(number)

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
        donation_form = self.context.donation_form
        if donation_form:
            html = self.context.unrestrictedTraverse(donation_form.split('/'))
            tabs.append({
                'id': donation_form,
                'label': u'Donate',
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
        local_campaign = self.context.get_fundraising_campaign()
        val = getattr(local_campaign, field, None)
        if not val:
            settings = get_settings()
            val = getattr(settings, field, None)
        # convert rich text objects, if present:
        if val and isinstance(val, RichTextValue):
            val = val.output

        return val

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

class PostDonationErrorView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.name('post_donation_error')
    grok.require('zope2.View')
    grok.template('post_donation_error')

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
        page = getattr(self.context, 'get_fundraising_campaign_page', None)
        if not page:
            return ''
        page = page()
        image_url = page.get_header_image_url()
        if not image_url:
            return ''
        return '<div id="fundraising-campaign-header-image"><a href="%s"><img src="%s/campaign_header" alt="%s" /></a></div>' % (
            page.absolute_url(), image_url, self.context.title)

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

# Temporary views used to do some migration from the old structure using Authorize.net and Recurly which were removed.
# These views will be deleted once the IP site migration is done

class CleanDonationCaches(grok.View):
    grok.context(IPloneSiteRoot)
    grok.name('clean-donation-caches')

    def render(self):
        pc = getToolByName(self.context, 'portal_catalog')
        res = pc.searchResults(
            object_provides='collective.salesforce.fundraising.fundraising_campaign.IFundraisingCampaignPage',
        )
        total = 0
        cleaned = 0
        skipped = 0
        for b in res:
            total += 1
            page = b.getObject()
            if not hasattr(page, '_memojito_'):
                skipped += 1
                continue
            key = ('get_donations', (page), frozenset([]))
            page._memojito_.clear()
            if page._memojito_.has_key(key):
                cleaned += 1
                del page._memojito_[key] 
            skipped += 1
        return '%i objects processed, %i cleaned, %i skipped' % (total, cleaned, skipped)

class SwitchToStripe(grok.View):
    grok.context(IPloneSiteRoot)
    grok.name('switch-to-stripe')

    def render(self):
        pc = getToolByName(self.context, 'portal_catalog')
        res = pc.searchResults(
            object_provides='collective.salesforce.fundraising.fundraising_campaign.IFundraisingCampaign',
        )
        total = 0
        switched = 0
        skipped = 0
        for b in res:
            total += 1
            page = b.getObject()
            new_forms = []
            for form in page.donation_form_tabs:
                # Keep product forms and donation products but ensure they use Stripe
                form_parts = form.split('|')[0].split('/')
                if len(form_parts) > 1:
                    # Only product and donation forms use a path
                    new_forms.append(form_parts[0] + '/donation_form_stripe')
                    continue
                # Skip all non-product forms
                skipped += 1
            if not new_forms:
                new_forms.append('donation_form_stripe')
            switched += 1
            page.donation_form_tabs = new_forms
        return '%i objects processed, %i switched, %i skipped' % (total, switched, skipped)
            

class CleanDonorOnlyUsers(grok.View):
    grok.context(IPloneSiteRoot)
    grok.name('clean-donor-only-users')

    def render(self):
        pc = getToolByName(self.context, 'portal_catalog')
        res = pc.searchResults(
            object_provides='collective.salesforce.fundraising.personal_campaign_page.IPersonalCampaignPage',
        )
        # Whitelist personal fundraisers
        whitelist = []
        for b in res:
            page = b.getObject()
            person = page.get_fundraiser()
            if person is not None:
                whitelist.append(person.email)

        # Add Administrators
        groups = getToolByName(self.context, 'portal_groups')
        admin = groups.getGroupById('Administrators')
        for member in admin.getGroupMembers():
            whitelist.append(member.getProperty('email'))

        to_delete = []
        res = pc.searchResults(portal_type='collective.salesforce.fundraising.person')
        for b in res:
            person = b.getObject()
            if person.email in whitelist:
                continue
            to_delete.append(person.id)
    
        if to_delete:
            self.context.people.manage_delObjects(to_delete)

        return '\n'.join(to_delete)
