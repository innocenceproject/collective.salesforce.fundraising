import locale
import random
from datetime import date

from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility

from zope.interface import Interface
from zope.interface import alsoProvides
from zope import schema
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent

from plone.z3cform.interfaces import IWrappedForm

from plone.app.textfield import RichText
from plone.namedfile import NamedBlobImage
from plone.namedfile.interfaces import IImageScaleTraversable

from Products.CMFCore.utils import getToolByName

from collective.salesforce.fundraising import MessageFactory as _
from collective.salesforce.fundraising.utils import get_settings

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

        # Only parse the dates if they have a value
        start_date = campaign.date_start
        if start_date:
            start_date = start_date.isoformat()
        end_date = campaign.date_end
        if end_date:
            end_date = end_date.isoformat()

        res = sfbc.create({
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
            })
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
        return True

    def add_donation(self, amount):
        """ Accepts an amount and adds the amount to the donations_total for this
            campaign and the parent campaign if this is a child campaign.  Also increments
            the donations_count by 1 for this campaign and the parent (if applicable).

            This should be considered temporary as the real amount will be synced periodically
            from salesforce via collective.salesforce.content.
        """
        if amount:
            amount = int(amount)
            self.donations_total = self.donations_total + amount
            self.donations_count = self.donations_count + 1

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
                    'label': label,
                    'html': html,
                })
        self.donation_form_tabs = tabs

class ThankYouView(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')
    grok.implements(IHideDonationForm)

    grok.name('thank-you')
    grok.template('thank-you')

    def update(self):
        # Fetch some values that should have been passed from the redirector
        self.email = self.request.form.get('email', None)
        self.first_name = self.request.form.get('first_name', None)
        self.last_name = self.request.form.get('last_name', None)
        self.amount = self.request.form.get('amount', None)

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
