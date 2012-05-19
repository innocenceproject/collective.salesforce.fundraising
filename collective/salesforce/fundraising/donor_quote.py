from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.site.hooks import getSite
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form

from plone.namedfile.interfaces import IImageScaleTraversable


# Interface class; used to define content-type schema.

class IDonorQuote(form.Schema, IImageScaleTraversable):
    """
    A quote from a donor about why they donated
    """

    form.model("models/donor_quote.xml")

    form.mode(email = 'hidden')
    email = schema.TextLine(title=u"Email")
alsoProvides(IDonorQuote, IContentType)


class DonorQuote(dexterity.Item):
    grok.implements(IDonorQuote)

    def get_container(self):
        if not self.campaign_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.campaign_sf_id)
        if not res:
            return None
        return res[0].getObject()

#class SampleView(grok.View):
#    grok.context(IDonorQuote)
#    grok.require('zope2.View')

    # grok.name('view')
