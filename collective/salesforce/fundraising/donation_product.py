from Acquisition import aq_base
from five import grok
from zope import schema
from zope.app.container.interfaces import IObjectAddedEvent
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.site.hooks import getSite
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from plone.directives import dexterity, form

from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.authnet.dpm import DonationFormAuthnetDPM as BaseDonationFormAuthnetDPM
from collective.salesforce.fundraising.utils import get_standard_pricebook_id

# Interface class; used to define content-type schema.

class IDonationProduct(form.Schema, IImageScaleTraversable):
    """
    A product such as a shirt or an event ticket which can be "purchased"
    through a donation form
    """

    form.model("models/donation_product.xml")

alsoProvides(IDonationProduct, IContentType)


@grok.subscribe(IDonationProduct, IObjectAddedEvent)
def handleDonationProductCreated(product, event):
    # don't accidentaly acquire the parent's sf_object_id when checking this
    if getattr(aq_base(product), 'sf_object_id', None) is None:
        sfbc = getToolByName(product, 'portal_salesforcebaseconnector')

        data = {
            'type': 'Product2',
            'ProductCode': product.id,
            'Description': product.description,
            'Name': product.title,
        }

        res = sfbc.create(data)
        if not res[0]['success']:
            raise Exception(res[0]['errors'][0]['message'])
        product.sf_object_id = res[0]['id']
        product.reindexObject(idxs=['sf_object_id'])
        # set up a pricebook entry for this object
        pricebook_id = get_standard_pricebook_id(sfbc)
        pedata = {'type': 'PricebookEntry',
                  'Pricebook2Id': pricebook_id,
                  'Product2Id': product.sf_object_id,
                  'UnitPrice': product.price}
        pe_res = sfbc.create(pedata)
        if not pe_res[0]['success']:
            req = product.REQUEST
            msg = u'Unable to set price for this product in salesforce'
            IStatusMessage(req).add(msg, type=u'warning')
    return


class DonationProduct(dexterity.Item):
    grok.implements(IDonationProduct)

    def get_container(self):
        if not self.campaign_sf_id:
            return None
        site = getSite()
        pc = getToolByName(site, 'portal_catalog')
        res = pc.searchResults(sf_object_id=self.campaign_sf_id)
        if not res:
            return None
        return res[0].getObject()

#class DonationProductView(grok.View):
#    grok.context(IDonationProduct)
#    grok.require('zope2.View')
#    grok.name('view')
#    grok.template('view')
   
class DonationFormAuthnetDPM(BaseDonationFormAuthnetDPM):
    grok.context(IDonationProduct)
    grok.require('zope2.View')
    grok.name('donation_form_authnet_dpm')
    grok.template('donation_form_authnet_dpm')
