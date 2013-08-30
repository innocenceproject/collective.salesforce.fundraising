from sets import Set
from zope import schema
from five import grok
from plone.directives import dexterity, form
from plone.supermodel import model

from Acquisition import aq_base
from Acquisition import aq_parent
from zope.component import getUtility
from zope.interface import alsoProvides
from zope.interface import Interface
from zope.app.content.interfaces import IContentType
from zope.app.container.interfaces import IObjectAddedEvent
from zope.lifecycleevent.interfaces import IObjectModifiedEvent

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from plone.app.textfield import RichText
from plone.app.layout.viewlets.interfaces import IPortalHeader
from plone.app.layout.viewlets.interfaces import IAboveContentBody
from plone import namedfile
from plone.namedfile.interfaces import IImageScaleTraversable
from plone.memoize import instance
from plone.uuid.interfaces import IUUID
from plone.uuid.interfaces import IUUIDAware
from plone.app.uuid.utils import uuidToObject
from plone.app.async.interfaces import IAsyncService
from plone.formwidget.contenttree.source import ObjPathSourceBinder
from dexterity.membrane.membrane_helpers import get_brains_for_email
from collective.chimpdrill.utils import IMailsnakeConnection
from collective.stripe.interfaces import IStripeEnabledView
from collective.stripe.interfaces import IStripeModeChooser

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import FundraisingCampaignPage
from collective.salesforce.fundraising.fundraising_campaign import CampaignView
from collective.salesforce.fundraising.fundraising_campaign import ShareView

from collective.salesforce.fundraising.utils import get_settings
from collective.salesforce.fundraising.utils import get_person_by_sf_id
from collective.salesforce.fundraising import MessageFactory as _

import logging
logger = logging.getLogger("Plone")

@grok.provider(schema.interfaces.IContextSourceBinder)
def availablePeople(context):
    query = {
        "portal_type": "collective.salesforce.fundraising.person",
    }
    return ObjPathSourceBinder(**query).__call__(context)

_marker = object()

# Interface class; used to define content-type schema.

class IPersonalCampaignPage(model.Schema, IImageScaleTraversable):
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

    image = namedfile.field.NamedBlobImage(
        title=_(u"Image"),
        description=_(u"Provide an image to use in promoting your campaign.  The image will show up on your page and also when someone shares your page on social networks."),
    )
    model.load("models/personal_campaign_page.xml")


alsoProvides(IPersonalCampaignPage, IContentType)

class IEditPersonalCampaignPage(form.Schema, IImageScaleTraversable):
    """
    Limited editing interface for a Personal Campaign Page
    """

    title = schema.TextLine(
        title=_(u"Title"),
        description=_(u"Provide a brief title for your campaign"),
    )
    description = schema.Text(
        title=_(u"Description"),
        description=_(u"Provide a 1-3 sentence pitch for your campaign.  This will be shown above the donation form on your page and as the description of your page when it is shared on social networks such as Facebook."),
    )
    image = namedfile.field.NamedBlobImage(
        title=_(u"Image"),
        description=_(u"Provide an image to use in promoting your campaign.  The image will show up on your page and also when someone shares your page on social networks.  Accepted format are jpg, gif, and png"),
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
    return data.context.get_fundraising_campaign().default_personal_appeal.output
        
@form.default_value(field=IPersonalCampaignPage['thank_you_message'])
def thankYouDefaultValue(data):
    return data.context.get_fundraising_campaign().default_personal_thank_you.output
        

class PersonalCampaignPage(dexterity.Container, FundraisingCampaignPage):
    grok.implements(IEditPersonalCampaignPage, IPersonalCampaignPage, IFundraisingCampaignPage)

    def absolute_url(self, do_not_cache=False):
        """ Fallback to cached value if no REQUEST available """
        url = super(PersonalCampaignPage, self).absolute_url()
        if do_not_cache:
            return url
        cached = getattr(aq_base(self), '_absolute_url', None)
        if url.startswith('http'):
            if cached is None or cached != url:
                self._absolute_url = url

        return getattr(aq_base(self), '_absolute_url', url)

    @property
    def donation_form(self):
        return self.get_fundraising_campaign().donation_form

    def is_personal(self):
        return True

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getUtility(ISiteRoot)
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.parent_sf_id, portal_type="collective.salesforce.fundraising.fundraisingcampaign")
        if not res:
            return None
        return res[0].getObject()

    def get_parent_sfid(self):
        return self.get_fundraising_campaign().sf_object_id

    def get_percent_goal(self):
        if self.goal and self.donations_total:
            return int((self.donations_total * 100) / self.goal)
        return 0

    def get_display_goal_pct(self):
        settings = get_settings()
        return settings.personal_campaign_status_completion_threshold

    def get_donations(self):
        pc = getToolByName(self, 'portal_catalog')
        res = pc.searchResults(
            portal_type = 'collective.salesforce.fundraising.donation', 
            path='/'.join(self.getPhysicalPath()), 
            sort_on='created', 
            sort_order='reverse'
        ) 
        return res

    def get_fundraiser(self):
        if not self.contact_sf_id:
            return 

        person = get_person_by_sf_id(self.contact_sf_id)
        return person

    def send_email_personal_page_created(self):
        campaign = self.get_fundraising_campaign()
        uuid = getattr(campaign, 'email_template_personal_page_created', None)
        if uuid is None:
            return

        template = uuidToObject(uuid)

        person = self.get_fundraiser()
        if person is None:
            return
   
        if not person.email:
            # Skip if we have no email to send to
            return
 
        data = self.get_email_campaign_data()

        return template.send(email = person.email,
            merge_vars = data['merge_vars'],
            blocks = data['blocks'],
        )

class PersonalCampaignPageView(CampaignView):
    grok.context(IPersonalCampaignPage)
    grok.implements(IStripeEnabledView)
    grok.require('zope2.View')

    grok.name('view')
    grok.template('view')

class PersonalCampaignPageCompactView(CampaignView):
    grok.context(IPersonalCampaignPage)
    grok.require('zope2.View')

    grok.name('compact_view')
    grok.template('compact_view')

class PersonalCampaignPageToolbarViewlet(grok.Viewlet):
    grok.name('collective.salesforce.fundraising.PersonalCampaignPageToolbar')
    grok.require('zope2.View')
    grok.context(IPersonalCampaignPage)
    grok.template('personal-campaign-toolbar')
    grok.viewletmanager(IPortalHeader)

    def update(self):
        # FIXME - I tried for hours to get checkPermission from the security manager to work to no avail... falling back to old school method
        pm = getToolByName(self.context, 'portal_membership')
        self.can_edit = pm.checkPermission('collective.salesforce.fundraising: Edit Personal Campaign', self.context)
        self.can_view_donors = pm.checkPermission('collective.salesforce.fundraising: View Personal Campaign Donors', self.context)
        self.can_promote = pm.checkPermission('collective.salesforce.fundraising: Promote Personal Campaign', self.context)

class PersonalCampaignPageFundraiserViewlet(grok.Viewlet):
    grok.name('collective.salesforce.fundraising.PersonalCampaignPageFundraiser')
    grok.require('zope2.View')
    grok.context(IPersonalCampaignPage)
    grok.template('personal-campaign-fundraiser')
    grok.viewletmanager(IAboveContentBody)

    def update(self):
        self.person = self.context.get_fundraiser()

class MyPersonalCampaignPagesList(grok.View):
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
        if self._person and self._person is not _marker:
            return self._person

        mtool = getToolByName(self.context, 'portal_membership')
        if mtool.isAnonymousUser():
            self._person = None
            return self._person
        
        member = mtool.getAuthenticatedMember()
        res = get_brains_for_email(self.context, member.id)
        if not res:
            return self._person

        self._person = res[0].getObject()
        return self._person

    def my_fundraisers(self):
        me = self.person()
        if not me:
            return []
        pc = getToolByName(self.context, 'portal_catalog')
        idvals = []
        user_id = getattr(me, 'id', None)
        if user_id:
            idvals.append(user_id)
        email = getattr(me, 'email', None)
        if email:
            idvals.append(email)
        my_uuid = None
        if IUUIDAware.providedBy(me):
            my_uuid = IUUID(me)
        if my_uuid:
            idvals.append(my_uuid)
        my_brains = pc(portal_type=self._fundraiser_type,
                       Creator=idvals, sort_order='reverse', sort_on='created')
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

        for b_donation in self.context.get_donations():
            donation = b_donation.getObject()
            is_thanked = b_donation.UID in thanked_donations
            
            first_name = donation.first_name
            last_name = donation.last_name
            email = donation.email
            phone = donation.phone
           
            payment_method = getattr(donation, 'payment_method', None)
            if payment_method not in [u'Cash',u'Check',u'Offline Credit Card']:
                payment_method = u'Online'

            self.donations.append({
                'name': '%s %s' % (first_name, last_name),
                'email': email,
                'phone': phone,
                'amount': donation.amount,
                'date': donation.get_friendly_date(),
                'id': b_donation.UID,
                'thanked': is_thanked,
                'payment_method': payment_method,
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

def mailchimpSubscribeFundraiser(page):
    campaign = page.get_fundraising_campaign()
    if not campaign.email_list_fundraisers:
        return

    logger.info("Mailchimp Subscribe: for Page %s" % page.title)

    person = page.get_fundraiser()
    if not person:
        # Skip if no person.  This can happen after initial save since the 
        # person field is set after the first save of the person
        logger.info("collective.salesforce.fundraising: Mailchimp Subscribe: skipping, no person yet")
        return

    percent = page.get_percent_goal()
    if not percent:
        percent = 0

    merge_vars = {
        'FNAME': person.first_name,
        'LNAME': person.last_name,
        'PF_GOAL': page.goal,
        'PF_TOTAL': page.donations_total,
        'PF_COUNT': page.donations_count,
        'PF_PERCENT': percent,
        'PF_REMAIN': 100 - percent,
        'PF_URL': page.absolute_url(),
    }
    logger.debug("collective.salesforce.fundraising: Mailchimp Subscribe: merge_vars = %s" % merge_vars)
    mc = getUtility(IMailsnakeConnection).get_mailchimp()
    res = mc.listSubscribe(
        id = campaign.email_list_fundraisers,
        email_address = person.email,
        merge_vars = merge_vars,
        update_existing = True,
        double_optin = False,
        send_welcome = False,
    )
    logger.info("collective.salesforce.fundraising: Mailchimp Subscribe: result = %s" % res)

@grok.subscribe(IPersonalCampaignPage, IObjectModifiedEvent)
def queueMailchimpSubscribeFundraiser(page, event):
    async = getUtility(IAsyncService)
    async.queueJob(mailchimpSubscribeFundraiser, page)

