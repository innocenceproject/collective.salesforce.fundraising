from datetime import date
from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from plone.z3cform.interfaces import IWrappedForm
from plone.app.textfield import RichText
from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage

from collective.salesforce.fundraising import MessageFactory as _


# Interface class; used to define content-type schema.

class IPersonalCampaignPage(form.Schema, IImageScaleTraversable):
    """
    A personal fundraising page
    """

    personal_appeal = RichText(
        title=u"Personal Appeal",
        description=u"Your donors will want to know why to donate to your campaign.  You can use the default text or personalize your appeal.  Remember, your page will mostly be visited by people who know you so a personalized message is often more effective",
    )    

    thank_you_message = RichText(
        title=u"Thank You Message",
        description=u"This message will be shown to your donors after they donate.  You can use the default text or personalize your thank you message",
    )    
    form.model("models/personal_campaign_page.xml")


alsoProvides(IPersonalCampaignPage, IContentType)

@form.default_value(field=IPersonalCampaignPage['personal_appeal'])
def personalAppealDefaultValue(data):
    context = data.context
    return context.default_personal_appeal
        
@form.default_value(field=IPersonalCampaignPage['thank_you_message'])
def thankYouDefaultValue(data):
    context = data.context
    return context.default_personal_thank_you
        


# Custom content-type class; objects created for this content type will
# be instances of this class. Use this class to add content-type specific
# methods and properties. Put methods that are mainly useful for rendering
# in separate view classes.

class PersonalCampaignPage(dexterity.Container):
    grok.implements(IPersonalCampaignPage, IFundraisingCampaignPage)

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getUtility(ISiteRoot)
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.parent_sf_id)
        if not res:
            return None
        return res[0].getObject()

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
            return '<script type="text/javascript">$(".campaign-goal .progress-bar").progressBar(%i);</script>' % self.get_percent_goal()

    def render_timeline_bar_js(self):
        if self.date_end:
            return '<script type="text/javascript">$(".campaign-timeline .progress-bar").progressBar(%i);</script>' % self.get_percent_timeline()

    def get_source_campaign(self):
        return 'Plone'

    def populate_form_embed(self):
        if self.form_embed:
            form_embed = self.form_embed
            form_embed = form_embed.replace('{{CAMPAIGN_ID}}', self.sf_object_id)
            form_embed = form_embed.replace('{{SOURCE_CODE}}', self.get_source_campaign())
            form_embed = form_embed.replace('{{SOURCE_URL}}', self.absolute_url())
            return form_embed

    def get_parent_sfid(self):
        return self.sf_object_id
