from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.component.hooks import getSite
from zope.app.content.interfaces import IContentType
from plone.namedfile.field import NamedImage
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form
from plone.supermodel import model

from plone.namedfile.interfaces import IImageScaleTraversable


# Interface class; used to define content-type schema.

class IDonorQuote(model.Schema, IImageScaleTraversable):
    """
    A quote from a donor about why they donated
    """
    image = NamedImage(
        title=u"Photo",
        description=u"(optional) Upload a photo to show with your quote.",
        required = False,
    )
    key = schema.TextLine(
        title=u"Donation Secret Key",
        description=u"The key used to authenticate to views on the Donation."
    )
    model.load("models/donor_quote.xml")
alsoProvides(IDonorQuote, IContentType)


class DonorQuote(dexterity.Item):
    grok.implements(IDonorQuote)

    def get_container(self):
        # FIXME: Figure out how to implement with containment in Donation object
        if not self.campaign_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(
            sf_object_id=self.campaign_sf_id, 
            portal_type = ['collective.salesforce.fundraising.fundraisingcampaign','collective.salesforce.fundraising.personalcampaignpage'],
        )
        if not res:
            return None
        return res[0].getObject()

class DonorQuoteView(grok.View):
    grok.context(IDonorQuote)
    grok.require('zope2.View')
    grok.name('view')
    grok.template('view')
    
