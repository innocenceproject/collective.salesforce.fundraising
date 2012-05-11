import locale
from datetime import date

from five import grok
from plone.directives import dexterity, form

from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent

from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from plone.app.textfield import RichText
from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.controlpanel.interfaces import IFundraisingSettings

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

    form.model("models/fundraising_campaign.xml")

alsoProvides(IFundraisingCampaign, IContentType)

@form.default_value(field=IFundraisingCampaign['thank_you_message'])
def thankYouDefaultValue(data):
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFundraisingSettings)
    return settings.default_thank_you_message

@form.default_value(field=IFundraisingCampaign['default_personal_appeal'])
def defaultPersonalAppealDefaultValue(data):
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFundraisingSettings)
    return settings.default_personal_appeal

@form.default_value(field=IFundraisingCampaign['default_personal_thank_you'])
def defaultPersonalThankYouDefaultValue(data):
    registry = getUtility(IRegistry)
    settings = registry.forInterface(IFundraisingSettings)
    return settings.default_personal_thank_you_message

# This is necessary because collective.salesforce.content never loads the
# form and thus never loads the default values on creation
@grok.subscribe(IFundraisingCampaign, IObjectAddedEvent)
def fillDefaultValues(campaign, event):
    if not campaign.thank_you_message:
        campaign.thank_you_message = thankYouDefaultValue(None)
        campaign.default_personal_appeal = defaultPersonalAppealDefaultValue(None)
        campaign.default_personal_thank_you = defaultPersonalThankYouDefaultValue(None)

class FundraisingCampaign(dexterity.Container):
    grok.implements(IFundraisingCampaign)

    def get_percent_goal(self):
        if self.goal and self.donations_total:
            return (self.donations_total * 100) / self.goal

    def get_percent_timeline(self):
        if self.date_start and self.date_end:
            today = date.today()
            if self.date_end < today:
                return 100
            if self.date_start > today:
                return 0

            delta_range = self.date_end - self.date_start
            delta_current = today - self.date_start
            return (delta_current.days * 100) / delta_range.days

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

    def render_goal_bar_js(self):
        if self.get_percent_goal():
            return '<script type="text/javascript">$(".campaign-progress-bar .progress-bar").progressbar({ value: %i});</script>' % self.get_percent_goal()

    def render_timeline_bar_js(self):
        if self.date_end:
            return '<script type="text/javascript">$(".campaign-timeline .progress-bar").progressbar({ value: %i});</script>' % self.get_percent_timeline()

    def get_source_code(self):
        return 'Plone'

    def populate_form_embed(self):
        if self.form_embed:
            form_embed = self.form_embed
            form_embed = form_embed.replace('{{CAMPAIGN_ID}}', getattr(self, 'sf_object_id', ''))
            form_embed = form_embed.replace('{{SOURCE_CODE}}', self.get_source_code())
            form_embed = form_embed.replace('{{SOURCE_URL}}', self.absolute_url())
            return form_embed

    def get_parent_sfid(self):
        return self.sf_object_id

    def get_fundraising_campaign(self):
        """ Returns the fundraising campaign object.  Useful for subobjects to easily lookup the parent campaign """
        return self

    def personal_fundraisers_count(self):
        """ Returns the number of personal campaign pages created off this campaign """
        return len(self.listFolderContents(contentFilter = {'portal_type': 'collective.salesforce.fundraising.personalcampaignpage'}))

    def create_personal_campaign_page_link(self):
        return self.absolute_url() + '/@@create-personal-campaign-page'

    def can_create_personal_campaign_page(self):
        # FIXME: add logic here to check for campaign status.  Only allow if the campaign is active
        return self.allow_personal

    def can_add_donor_quote(self):
        return True

    def show_employer_matching(self):
        return True

class CampaignView(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

    def addcommas(self, number):
        locale.setlocale(locale.LC_ALL, '')
        return locale.format('%d', number, 1)

class ThankYouView(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('zope2.View')

    grok.name('thank-you')
    grok.template('thank-you')

