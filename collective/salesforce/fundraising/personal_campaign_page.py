from sets import Set
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
from plone.memoize import instance

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign
from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import FundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import CampaignView
from collective.salesforce.fundraising.fundraising_campaign import ShareView

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

DONATIONS_SOQL = """SELECT
  OpportunityId,
  Opportunity.Amount,
  Opportunity.CloseDate,
  Contact.FirstName,
  Contact.LastName,
  Contact.Email,
  Contact.Phone
from OpportunityContactRole
where
  IsPrimary = true
  and Opportunity.CampaignId = '%s'
  and Opportunity.IsWon = true
"""


class PersonalCampaignPage(dexterity.Container, FundraisingCampaignPage):
    grok.implements(IPersonalCampaignPage, IFundraisingCampaignPage)

    @property
    def donation_form_tabs(self):
        return self.get_fundraising_campaign().donation_form_tabs

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

    @instance.memoize
    def get_donations(self):
        sfbc = getToolByName(self, 'portal_salesforcebaseconnector')
        return sfbc.query(DONATIONS_SOQL % (self.sf_object_id))

    def clear_donations_from_cache(self):
        """ Clears the donations cache.  This should be called anytime a new donation comes in 
            for the campaign so a fresh list is pulled after any changes """
        key = ('get_donations', (self), frozenset([]))
        self._memojito_.clear()
        if self._memojito_.has_key(key):
            del self._memojito_[key]

class PersonalCampaignPageView(CampaignView):
    grok.context(IPersonalCampaignPage)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

class PersonalCampaignPagesList(grok.View):
    grok.context(IFundraisingCampaignPage)
    grok.require('zope2.View')

    grok.name('compact_view')
    grok.template('compact_view')

class MyDonorsView(grok.View):
    grok.context(IPersonalCampaignPage)
    grok.require('collective.salesforce.fundraising.ManagePersonalCampaign')

    grok.name('donors')
    grok.template('donors')

    def update(self):
        self.donations = []
        self.count_donations = 0
        self.count_thanked = 0
        self.count_not_thanked = 0
        thanked_donations = getattr(self.context, 'thanked_donations', [])
        if thanked_donations == None:
            thanked_donations = []

        for donation in self.context.get_donations():
            is_thanked = donation['OpportunityId'] in thanked_donations
            self.donations.append({
                'name': '%s %s' % (donation['Contact']['FirstName'], donation['Contact']['LastName']),
                'email': donation['Contact']['Email'],
                'phone': donation['Contact']['Phone'],
                'amount': donation['Opportunity']['Amount'],
                'date': donation['Opportunity']['CloseDate'],
                'id': donation['OpportunityId'],
                'thanked': is_thanked,
            })
            self.count_donations += 1
            if is_thanked:
                self.count_thanked += 1
            else:
                self.count_not_thanked += 1
            

class SaveThankedStatusView(grok.View):
    """ A simple view meant to be called via AJAX when a fundraiser has marked
        a set of donations as either thanked or not thanked """
    grok.context(IPersonalCampaignPage)
    grok.require('collective.salesforce.fundraising.ManagePersonalCampaign')
    grok.name('save_thanked_status')

    def render(self):
        thanked_ids = self.request.form.get('thanked', '')
        not_thanked_ids = self.request.form.get('not_thanked', '')

        thanked_ids = Set(thanked_ids.split(','))
        not_thanked_ids = Set(not_thanked_ids.split(','))

        thanked_donations = getattr(self.context, 'thanked_donations', [])
        if thanked_donations == None:
            thanked_donations = []
        thanked_donations = Set(thanked_donations)

        thanked_donations.update(thanked_ids)
        thanked_donations.difference_update(not_thanked_ids)

        self.context.thanked_donations = list(thanked_donations)
        return 'OK'

class PromoteCampaignView(ShareView):
    grok.context(IPersonalCampaignPage)
    grok.require('collective.salesforce.fundraising.ManagePersonalCampaign')

    grok.name('promote')
    grok.template('promote')

