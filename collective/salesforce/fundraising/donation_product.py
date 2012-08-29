from five import grok
from zope import schema
from zope.interface import alsoProvides
from zope.component import getUtility
from zope.site.hooks import getSite
from zope.app.content.interfaces import IContentType
from Products.CMFCore.utils import getToolByName
from plone.directives import dexterity, form

from plone.namedfile.interfaces import IImageScaleTraversable

from collective.salesforce.fundraising.authnet.dpm import DonationFormAuthnetDPM as BaseDonationFormAuthnetDPM
from collective.salesforce.fundraising.authnet.dpm import AuthnetFingerprint as BaseAuthnetFingerprint


# Interface class; used to define content-type schema.

class IDonationProduct(form.Schema, IImageScaleTraversable):
    """
    A product such as a shirt or an event ticket which can be "purchased"
    through a donation form
    """

    form.model("models/donation_product.xml")

alsoProvides(IDonationProduct, IContentType)


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

    def update(self):
        super(DonationFormAuthnetDPM, self).update()
        self.quantity = self.request.form.get('c_quantity', None)
        if self.quantity == None:
            self.quantity = 0
        self.amount = self.context.price * self.quantity
        self.fingerprint_url = self.context.get_fundraising_campaign().absolute_url() + '/authnet_fingerprint'

    def update_levels(self):
        level_id = self.request.form.get('product_levels', self.settings.default_product_ask)
        self.levels = None
        for row in self.settings.product_ask_levels:
            row_id, amounts = row.split('|')
            if row_id == level_id:
                self.levels = amounts.split(',')
        if not self.levels:
            self.levels = self.settings.product_ask_levels[0].split('|')[1].split(',')

class AuthnetFingerprint(BaseAuthnetFingerprint):
    grok.context(IDonationProduct)

    def update(self):
        super(AuthnetFingerprint, self).update()

