from five import grok
from plone.directives import dexterity, form

from plone.namedfile.interfaces import IImageScaleTraversable


# Interface class; used to define content-type schema.

class IDonorQuote(form.Schema, IImageScaleTraversable):
    """
    A quote from a donor about why they donated
    """

    form.model("models/donor_quote.xml")

class DonorQuote(dexterity.Item):
    grok.implements(IDonorQuote)

    def get_container(self):
        if not self.parent_sf_id:
            return None
        site = getUtility(ISiteRoot)
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.parent_sf_id)
        if not res:
            return None
        return res[0].getObject()

#class SampleView(grok.View):
#    grok.context(IDonorQuote)
#    grok.require('zope2.View')

    # grok.name('view')
