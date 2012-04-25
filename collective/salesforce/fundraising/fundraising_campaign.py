import locale
from datetime import date

from five import grok
from plone.directives import dexterity, form

from zope import schema
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from zope.schema.interfaces import IContextSourceBinder
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from zope.interface import invariant, Invalid

from z3c.form import group, field

from plone.namedfile.interfaces import IImageScaleTraversable
from plone.namedfile.field import NamedImage, NamedFile
from plone.namedfile.field import NamedBlobImage, NamedBlobFile

from plone.app.textfield import RichText

from z3c.relationfield.schema import RelationList, RelationChoice
from plone.formwidget.contenttree import ObjPathSourceBinder

from collective.salesforce.fundraising import MessageFactory as _


# Interface class; used to define content-type schema.

class IFundraisingCampaign(form.Schema, IImageScaleTraversable):
    """
    A Fundraising Campaign linked to a Campaign in Salesforce.com
    """
    
    form.model("models/fundraising_campaign.xml")

alsoProvides(IFundraisingCampaign, IContentType)


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
            #return '<script type="text/javascript">$(".campaign-progress-bar .progress-bar").progressBar(%i, {width: 250, height: 30, showText: false, boxImage: "++resource++collective.salesforce.fundraising/jquery.progressbar/images/progressbar-background.png", barImages: {0: "++resource++collective.salesforce.fundraising/jquery.progressbar/images/progressbar-green.png"}});</script>' % self.get_percent_goal()
            return '<script type="text/javascript">$(".campaign-progress-bar .progress-bar").progressbar({ value: %i});</script>' % self.get_percent_goal()

    def render_timeline_bar_js(self):
        if self.date_end:
            return '<script type="text/javascript">$(".campaign-timeline .progress-bar").progressbar({ value: %i});</script>' % self.get_percent_timeline()

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

    def get_fundraising_campaign(self):
        """ Returns the fundraising campaign object.  Useful for subobjects to easily lookup the parent campaign """
        return self


class CampaignView(grok.View):
    grok.context(IFundraisingCampaign)
    grok.require('zope2.View')
    
    grok.name('view')
    grok.template('view')

    def addcommas(self, number):
        locale.setlocale(locale.LC_ALL, '')
        return locale.format('%d', number, 1)

class CreatePersonalCampaignPageView(grok.View):
    grok.context(IFundraisingCampaign)
    # FIXME - make this a custom permission so it can be controlled by the workflow
    grok.require('zope2.View')
    grok.name('create_personal_campaign')
    grok.template('create_personal_campaign')

    @property
    def form(self):
        from collective.salesforce.fundraising.forms import CreatePersonalCampaignPageForm
        form = CreatePersonalCampaignPageForm(self.request)
        return form

