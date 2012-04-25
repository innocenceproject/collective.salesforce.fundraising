from five import grok
from plone.directives import dexterity, form

from zope import schema
from zope.component import getUtility
from zope.interface import alsoProvides
from zope.app.content.interfaces import IContentType
from zope.schema.interfaces import IContextSourceBinder
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from zope.interface import invariant, Invalid

from z3c.form import group, field

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName

from plone.namedfile.interfaces import IImageScaleTraversable
from plone.namedfile.field import NamedImage, NamedFile
from plone.namedfile.field import NamedBlobImage, NamedBlobFile

from plone.app.textfield import RichText

from z3c.relationfield.schema import RelationList, RelationChoice
from plone.formwidget.contenttree import ObjPathSourceBinder

from collective.salesforce.fundraising import MessageFactory as _


# Interface class; used to define content-type schema.

class IPersonalCampaignPage(form.Schema, IImageScaleTraversable):
    """
    A personal fundraising page
    """
    
    # If you want a schema-defined interface, delete the form.model
    # line below and delete the matching file in the models sub-directory.
    # If you want a model-based interface, edit
    # models/personal_campaign_page.xml to define the content type
    # and add directives here as necessary.
    
    form.model("models/personal_campaign_page.xml")
alsoProvides(IPersonalCampaignPage, IContentType)


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
        res = pc.searchResults(sf_object_id = self.parent_sf_id)
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
