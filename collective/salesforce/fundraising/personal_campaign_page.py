from datetime import date
from five import grok
from plone.directives import dexterity, form

from zope.component import getUtility
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from plone.app.textfield import RichText
from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.fundraising_campaign import IFundraisingCampaign


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
    grok.implements(IPersonalCampaignPage)

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

    def get_source_code(self):
        return 'Plone'

    def populate_form_embed(self):
        if self.form_embed:
            form_embed = self.form_embed
            form_embed = form_embed.replace('{{CAMPAIGN_ID}}', self.sf_object_id)
            form_embed = form_embed.replace('{{SOURCE_CODE}}', self.get_source_code())
            form_embed = form_embed.replace('{{SOURCE_URL}}', self.absolute_url())
            return form_embed

    def get_parent_sfid(self):
        return self.sf_object_id

# View class
# The view will automatically use a similarly named template in
# personal_campaign_page_templates.
# Template filenames should be all lower case.
# The view will render when you request a content object with this
# interface with "/@@sampleview" appended.
# You may make this the default view for content objects
# of this type by uncommenting the grok.name line below or by
# changing the view class name and template filename to View / view.pt.


class SampleView(grok.View):
    grok.context(IPersonalCampaignPage)
    grok.require('zope2.View')

    # grok.name('view')


class ThankYouView(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('zope2.View')

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
