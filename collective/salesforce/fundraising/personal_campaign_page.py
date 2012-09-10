from sets import Set
from zope import schema
from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility
from zope.interface import alsoProvides
from zope.interface import Interface
from zope.app.content.interfaces import IContentType

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from plone.app.textfield import RichText
from plone.app.layout.viewlets.interfaces import IAboveContent
from plone import namedfile
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.memoize import instance
from plone.uuid.interfaces import IUUID
from plone.uuid.interfaces import IUUIDAware
from dexterity.membrane.membrane_helpers import get_membrane_user

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import FundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import CampaignView
from collective.salesforce.fundraising.fundraising_campaign import ShareView

from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising import MessageFactory as _


_marker = object()

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

class IEditPersonalCampaignPage(form.Schema, IImageScaleTraversable):
    """
    Limited editing interface for a Personal Campaign Page
    """

    title = schema.TextLine(
        title=_(u"Title"),
        description=_(u"Provide a brief title for your campaign"),
    )
    description = schema.TextLine(
        title=_(u"Description"),
        description=_(u"Provide a 1-3 sentence pitch for your campaign"),
    )
    image = namedfile.field.NamedBlobImage(
        title=_(u"Image"),
        description=_(u"Provide an image to use in promoting your campaign.  The image will show up on your page and also when someone shares your page on social networks."),
    )
    goal = schema.Int(
        title=_(u"Goal"),
        description=_(u"Set the dollar amount goal you aim to raise in your campaign"),
    )
    personal_appeal = RichText(
        title=u"Personal Appeal",
        description=u"Your donors will want to know why to donate to your campaign.  You can use the default text or personalize your appeal.  Remember, your page will mostly be visited by people who know you so a personalized message is often more effective",
    )    

    thank_you_message = RichText(
        title=u"Thank You Message",
        description=u"This message will be shown to your donors after they donate.  You can use the default text or personalize your thank you message",
    )    

@form.default_value(field=IPersonalCampaignPage['personal_appeal'])
def personalAppealDefaultValue(data):
    return get_settings().default_personal_appeal
        
@form.default_value(field=IPersonalCampaignPage['thank_you_message'])
def thankYouDefaultValue(data):
    return get_settings().default_personal_thank_you_message
        


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
    grok.implements(IEditPersonalCampaignPage, IPersonalCampaignPage, IFundraisingCampaignPage)

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
        if not hasattr(self, '_memojito_'):
            return None
        key = ('get_donations', (self), frozenset([]))
        self._memojito_.clear()
        if self._memojito_.has_key(key):
            del self._memojito_[key]

class PersonalCampaignPageView(CampaignView):
    grok.context(IPersonalCampaignPage)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

class PersonalCampaignPageToolbarViewlet(grok.Viewlet):
    grok.name('collective.salesforce.fundraising.PersonalCampaignPageToolbar')
    grok.require('zope2.View')
    grok.context(IPersonalCampaignPage)
    grok.template('personal-campaign-toolbar')
    grok.viewletmanager(IAboveContent)

    def update(self):
        # FIXME - I tried for hours to get checkPermission from the security manager to work to no avail... falling back to old school method
        pm = getToolByName(self.context, 'portal_membership')
        self.can_edit = pm.checkPermission('collective.salesforce.fundraising: Edit Personal Campaign', self.context)
        self.can_view_donors = pm.checkPermission('collective.salesforce.fundraising: View Personal Campaign Donors', self.context)
        self.can_promote = pm.checkPermission('collective.salesforce.fundraising: Promote Personal Campaign', self.context)

class PersonalCampaignPagesList(grok.View):
    """This view is accessible from anywhere in the site, do not write 
    template code for it that assumes a fundraiser as the context
    """
    grok.context(Interface)
    grok.require('zope2.View')

    grok.name('my_fundraisers')
    grok.template('my_fundraisers')

    _person = _marker
    _fundraiser_type = 'collective.salesforce.fundraising.personalcampaignpage'
    
    def update(self):
        self.fundraisers = self.my_fundraisers()
    
    def person(self):
        """provide access to the logged-in user
        """
        if self._person is not _marker:
            return self._person

        mtool = getToolByName(self.context, 'portal_membership')
        if mtool.isAnonymousUser():
            self._person = None
            return self._person
        
        member = mtool.getAuthenticatedMember()
        person = get_membrane_user(self.context, member.id,
                                   'collective.salesforce.fundraising.person',
                                   get_object=True)
        self._person = person
        return self._person

    def my_fundraisers(self):
        me = self.person()
        if not me:
            return []
        pc = getToolByName(self.context, 'portal_catalog')
        idvals = me.id
        my_uuid = None
        if IUUIDAware.providedBy(me):
            my_uuid = IUUID(me)
        if my_uuid:
            idvals = [idvals, my_uuid]
        my_brains = pc(portal_type=self._fundraiser_type,
                       Creator=idvals)
        return [b.getObject() for b in my_brains]

class MyDonorsView(grok.View):
    grok.context(IPersonalCampaignPage)
    grok.require('collective.salesforce.fundraising.ViewPersonalCampaignDonors')

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
    grok.require('collective.salesforce.fundraising.ViewPersonalCampaignDonors')
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
    grok.require('collective.salesforce.fundraising.PromotePersonalCampaign')

    grok.name('promote')
    grok.template('promote')

class PageConfirmationEmailView(grok.View):
    grok.context(IPersonalCampaignPage)

    grok.name('page-confirmation-email')
    grok.template('page_confirmation_email')

    def set_page_values(self, data):
        self.data = data
