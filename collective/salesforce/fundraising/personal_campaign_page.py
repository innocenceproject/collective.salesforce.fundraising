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
from collective.salesforce.fundraising.fundraising_campaign import FundraisingCampaignPage

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

class PersonalCampaignPage(dexterity.Container, FundraisingCampaignPage):
    grok.implements(IPersonalCampaignPage, IFundraisingCampaignPage)

    @property
    def donation_form_tabs(self):
        return self.__parent__.donation_form_tabs

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getUtility(ISiteRoot)
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.parent_sf_id)
        if not res:
            return None
        return res[0].getObject()

    def get_parent_sfid(self):
        return self.aq_parent.sf_object_id

    def populate_form_embed(self):
        if self.aq_parent.form_embed:
            form_embed = self.aq_parent.form_embed
            form_embed = form_embed.replace('{{CAMPAIGN_ID}}', getattr(self, 'sf_object_id', ''))
            form_embed = form_embed.replace('{{SOURCE_CAMPAIGN}}', self.get_source_campaign())
            form_embed = form_embed.replace('{{SOURCE_URL}}', self.get_source_url())
            return form_embed

    def get_percent_goal(self):
        if self.goal and self.donations_total:
            return int((self.donations_total * 100) / self.goal)
        return 0

class PersonalCampaignPagesList(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('compact_view')
    grok.template('compact_view')
